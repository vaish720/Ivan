# Research: free and free-tier API stack for the sales voice assistant
_Researched 2026-10-27 from primary sources (official docs, pricing pages, GitHub repos). Prices and quotas change often, so re-check them before you commit to a vendor._

**Question:** which APIs and libraries can deliver these features for sales reps on Microsoft 365, starting from free options?
- voice commands for meetings
- reminders
- post-meeting follow-ups with memory
- end-of-day summary
- Outlook + Teams triage
- Teams calls
- a Teams bot

## Three findings that change the plan
1. **The free M365 E5 developer sandbox is no longer open to everyone.** Only these groups get it:
   - Visual Studio Professional/Enterprise subscribers
   - ISV Success / AI Cloud Partner Program partners
   - Premier/Unified Support customers

   A billing account must be linked. The tenant lasts up to 90 days and renews only while you stay eligible. Source: [M365 Developer Program FAQ](https://learn.microsoft.com/en-us/office/developer-program/microsoft-365-developer-program-faq) (updated 2026-09-04).
2. **Teams Graph APIs are no longer metered** (since 2025-08-25). Source: [Metered API list](https://learn.microsoft.com/en-us/graph/metered-api-list).
3. **The Bot Framework SDK is retired.** Its final long-term support ended December 2025, and the repo was archived on 2026-01-05. Use the **Microsoft 365 Agents SDK** instead. Source: [botframework-sdk on GitHub](https://github.com/microsoft/botframework-sdk).

## 1. Microsoft Graph

### 1a. Developer tenant options
- **E5 sandbox:** only if Collabera (or you) qualify under finding 1. It includes 25 licenses, sample data and Teams Phone. ([FAQ](https://learn.microsoft.com/en-us/office/developer-program/microsoft-365-developer-program-faq))
- **Microsoft 365 Business trial tenant:** the fallback. _Current trial terms were not verified._
- **Agents Playground:** tests the bot's chat UI without any M365 account. ([Agents Toolkit](https://learn.microsoft.com/en-us/microsoftteams/platform/toolkit/teams-toolkit-fundamentals))

### 1b. Endpoints and permissions per feature
| Feature | Endpoint | Delegated permission | Needs admin consent? |
|---|---|---|---|
| Create / move / delete Teams meeting | `POST/PATCH/DELETE /me/events` with `isOnlineMeeting: true`, `onlineMeetingProvider: "teamsForBusiness"` | Calendars.ReadWrite | No |
| Find a slot | `POST /me/findMeetingTimes` (delegated only, no application permission) | Calendars.Read.Shared | No |
| Mail triage | `/me/messages`, `/me/mailFolders('inbox')/messages/delta` | Mail.Read / Mail.ReadWrite | No |
| Teams chat messages | `GET /me/chats/{id}/messages` | Chat.Read | No |
| Channel messages | channel messages API | ChannelMessage.Read.All | **Yes** |
| Meeting transcripts | `GET /me/onlineMeetings/{id}/transcripts`, then `/{id}/content` | OnlineMeetingTranscript.Read.All | **Yes** |
| Reminders | `/me/todo/lists/{id}/tasks` | Tasks.ReadWrite | No |

Sources and notes:
- **Online meetings:** once a meeting is made online, it can't be switched back. The join URL is in `onlineMeeting.joinUrl`. ([Online meetings in Outlook calendar](https://learn.microsoft.com/en-us/graph/outlook-calendar-online-meetings))
- **findMeetingTimes:** [user: findMeetingTimes](https://learn.microsoft.com/en-us/graph/api/user-findmeetingtimes?view=graph-rest-1.0) (updated 2026-06).
- **Triage signals on a message:** `importance` (low/normal/high), `inferenceClassification` (focused/other), `flag` (follow-up status + due date), `isRead`, `categories`, `conversationId`. ([message resource](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0))
- **Chat message listing:** `$top` is 50 at most. A date filter only works when `$orderby` uses the same field. ([List chat messages](https://learn.microsoft.com/en-us/graph/api/chat-list-messages?view=graph-rest-1.0))
- **Transcripts:** ([List transcripts](https://learn.microsoft.com/en-us/graph/api/onlinemeeting-list-transcripts?view=graph-rest-1.0))
  - Only for meetings tied to a calendar event, and only until the meeting expires.
  - The tenant admin must allow Graph access to transcripts, otherwise the call returns 403 `GraphAccessToTranscriptsDisabled`.
  - Application access also needs an application access policy.
- **`getAllTranscripts`:** application permission only, supports delta, and covers only meetings the user organised. ([getAllTranscripts](https://learn.microsoft.com/en-us/graph/api/onlinemeeting-getalltranscripts?view=graph-rest-1.0), updated 2026-08-13)
- **Delta queries** are available for message, event, chatMessage, callTranscript, todoTask and todoTaskList. Outlook delta tokens have no fixed lifetime and can be evicted. ([Delta query overview](https://learn.microsoft.com/en-us/graph/delta-query-overview))
- **To Do tasks** support reminders, with both delegated and application permissions. ([To Do API overview](https://learn.microsoft.com/en-us/graph/api/resources/todo-overview?view=graph-rest-1.0), updated 2026-10-22)

### 1c. Metered and protected APIs
- **Metered:** the only one left is SharePoint `assignSensitivityLabel`, at $0.00185 per call. ([Metered API list](https://learn.microsoft.com/en-us/graph/metered-api-list))
- **Protected:** `chats/getAllMessages` and other export APIs are application-only and need an access-request form. _Not verified:_ Microsoft's protected-API doc page returned 404. **Design choice:** avoid them and read each chat with delegated permission.

### 1d. Authentication
- Use **MSAL with delegated permissions plus `offline_access`** for the MVP. Every core feature uses permissions a user can approve without an admin.
- These need an admin regardless: OnlineMeetingTranscript.Read.All, ChannelMessage.Read.All, all application permissions, and all `Calls.*` permissions. ([Permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference))

## 2. Placing calls through Teams
| Route | What it does | Cost / constraints | Fit |
|---|---|---|---|
| **Deep link** `https://teams.microsoft.com/l/call/0/0?users=a@x.com,4:<phone>&withVideo=true` | Opens a Teams call to one or more people; `4:` prefix for phone numbers. Teams asks the user to confirm before dialling. Can't start meetings. | Free | **MVP** ([Deep-link workflow](https://learn.microsoft.com/en-us/microsoftteams/platform/concepts/build-and-test/deep-link-workflow), 2026-06-23) |
| **Chat deep link** `…/l/chat/0/0?users=…&topicName=…&message=…` | Opens a chat with the topic pre-filled | Free | MVP, for "message X about Y" |
| **Graph calling bot, service-hosted media** | Bot starts calls (1:1, group, phone) and joins meetings; can play prompts, record, and detect keypad tones | Calls.* application permissions (admin) | Phase 6: play a pre-recorded brief ([Calls & meetings bots overview](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/calls-and-meetings/calls-meetings-bots-overview)) |
| **Graph calling bot, app-hosted media** | Real-time two-way audio (a live conversation) | **C#/.NET only**, Windows Server VMs on Azure (not Web Apps), public IP, ≥2 cores, media library within 3 months of latest | Phase 6 option B ([Requirements](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/calls-and-meetings/requirements-considerations-application-hosted-media-bots)) |
| **Azure Communication Services** | Can call Teams users with a Teams identity; "Start a call on behalf of the Teams user" is **not supported** | $0.004 per participant per minute; US phone calls ~$0.013/min (example figures); Teams users' own usage free | Phase 6 option A ([ACS pricing concepts](https://learn.microsoft.com/en-us/azure/communication-services/concepts/pricing), [pricing page](https://azure.microsoft.com/en-us/pricing/details/communication-services/), [Teams-user calling](https://learn.microsoft.com/en-us/azure/communication-services/concepts/interop/teams-user-calling)) |

## 3. Teams bot
- **Microsoft 365 Agents SDK:** C# (.NET 8), Node 18+, Python 3.9–3.11. It handles channels (Teams, Copilot, web, Slack) and conversation state, and works with any AI service. ([Agents SDK overview](https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/agents-sdk-overview), updated 2026-10-16)
- **Agents Toolkit** (formerly Teams Toolkit) is a free VS Code extension. TeamsFx is deprecated, with community support until 2026-09. ([Toolkit fundamentals](https://learn.microsoft.com/en-us/microsoftteams/platform/toolkit/teams-toolkit-fundamentals))
- **Azure Bot Service F0** gives unlimited messages on standard channels, and Teams is one. Premium channels get 10K messages a month. ([Bot Service pricing](https://azure.microsoft.com/en-us/pricing/details/bot-services/))
- **Joining meetings or real-time voice** is only possible through a calling bot (section 2). The Agents SDK alone doesn't do it.

## 4. Free voice stack
| Option | Type | Free allowance / license | Source |
|---|---|---|---|
| Web Speech API | STT in the browser | Free; on-device where supported; browser support varies | [MDN](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API) (2026-08-19) |
| **faster-whisper** | Local STT | MIT; up to 4× faster than Whisper; int8 on CPU | [GitHub](https://github.com/SYSTRAN/faster-whisper) |
| Groq Whisper (large-v3 / v3-turbo) | Cloud STT | Free tier: 20 req/min, 2K req/day, 7.2K audio-sec/hr, 28.8K audio-sec/day | [Groq rate limits](https://console.groq.com/docs/rate-limits) |
| Azure AI Speech F0 | Cloud STT + TTS | 5 hours of STT and 0.5M characters of neural TTS per month | [Azure Speech pricing](https://azure.microsoft.com/en-us/pricing/details/cognitive-services/speech-services/) |
| Deepgram | Cloud STT + TTS | $200 credit (no expiry, no card); Nova-3 streaming $0.0048/min; Aura-2 $0.030 per 1K characters | [Deepgram pricing](https://deepgram.com/pricing) |
| AssemblyAI | Cloud STT | $50 credit; streaming $0.15–0.45/hr | [AssemblyAI pricing](https://www.assemblyai.com/pricing) |
| **Kokoro** | Local TTS | Apache-2.0, 82M parameters | [GitHub](https://github.com/hexgrad/kokoro) |
| Piper | Local TTS | **GPL-3.0** | [GitHub](https://github.com/OHF-Voice/piper1-gpl) |
| edge-tts | TTS | GPL-3.0; uses Edge's online service **unofficially**. Avoid for anything shipped. | [GitHub](https://github.com/rany2/edge-tts) |
| ElevenLabs | Cloud TTS | 10K credits a month, **no commercial license** on the free plan; Starter $6/month | [ElevenLabs pricing](https://elevenlabs.io/pricing) |

**Voice frameworks**
- **Pipecat** (BSD-2): voice pipeline, Silero voice detection, transports (SmallWebRTC, WebSocket, Daily, LiveKit), 20+ STT / 30+ LLM / 25+ TTS integrations. ([GitHub](https://github.com/pipecat-ai/pipecat))
- **LiveKit Agents** (Apache-2.0; its turn-detector model has its own license): semantic turn detection, phone (SIP) calling, MCP. Self-hosted or LiveKit Cloud. ([GitHub](https://github.com/livekit/agents))

## 5. LLM with tool calling
- **Ollama (local):** tool calling via `/api/chat`, including streaming and parallel calls; the docs use qwen3 as the example. Free and private. ([Ollama tool calling](https://docs.ollama.com/capabilities/tool-calling))
- **Groq free tier:** gpt-oss-120b / gpt-oss-20b / qwen3.8-27b, each 30 req/min, 1K req/day, 8K tokens/min, 200K tokens/day. No Llama chat models on the free plan. ([Groq rate limits](https://console.groq.com/docs/rate-limits)) _Not verified: whether tool use is enabled on the free tier, and Groq's data-retention terms._
- **Gemini free tier:** free tiers exist for several Flash, Flash-Lite and 2.5 models plus Embedding 2. Free-tier content "may be used to improve our products", so **don't send client mail or chats there.** Flash prices change on 2026-12-01. The exact free quotas are shown only in AI Studio. ([Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing), [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)) _Not verified: exact model names._
- **Claude (paid, later)** ([models](https://platform.claude.com/docs/en/about-claude/models/overview), [pricing](https://platform.claude.com/docs/en/about-claude/pricing)):

| Model ID | Input / output per million tokens |
|---|---|
| `claude-haiku-5-5` | $0.10 / $0.50 for prompts up to 100K tokens; $0.50 / $2.50 above that |
| `claude-sonnet-5-5` | $2 / $10 |
| `claude-opus-5-5` | $4 / $20 |
| `claude-fable-5-1` | $10 / $50 |

  - The Batch API is 50% off.
  - Cache reads cost 0.05× the input price on Opus 5.5 / Sonnet 5.5, and 0.1× on Haiku 5.5.

## 6. Memory (vector store and embeddings)
| Option | License / notes | Source |
|---|---|---|
| sqlite-vec | MIT/Apache-2.0; pre-v1, so breaking changes are expected | [GitHub](https://github.com/asg017/sqlite-vec) |
| Chroma | Apache-2.0; embedded `PersistentClient` | [GitHub](https://github.com/chroma-core/chroma) |
| Qdrant | Apache-2.0 | [GitHub](https://github.com/qdrant/qdrant) |
| pgvector | v0.8.7; HNSW and IVFFlat indexes; the target once hosted on Postgres | [GitHub](https://github.com/pgvector/pgvector) |
| nomic-embed-text-v1.5 | Apache-2.0; 8,192-token context; 64–768 dimensions; works with sentence-transformers | [Hugging Face](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5) |

## 7. Scheduling and proactive triggers
- **APScheduler:** use 3.11.3 (MIT, released 2026-06-28). 4.0 is still alpha (4.0.0a6). ([PyPI](https://pypi.org/project/APScheduler/))
- **Graph webhooks (change notifications):** ([Change notifications overview](https://learn.microsoft.com/en-us/graph/change-notifications-overview))
  - Maximum subscription lifetimes:

    | Resource | Max lifetime |
    |---|---|
    | Mail, events, contacts | 10,080 min (under 7 days) |
    | Mail, events, contacts, with the data included in the notification | 1,440 min |
    | Chats, chat messages, transcripts | 4,320 min (3 days) |
    | To Do tasks | 4,230 min |

  - Chat and chat-message subscriptions are capped at 10 per user.
  - Typical delay: mail under 1 minute, chat messages under 10 seconds.
- **Pattern:** a webhook says something changed → a delta query pulls the changes → a scheduled job renews the subscriptions. Until a public URL exists, scheduled delta polling is enough.

## Recommended free MVP stack
- **Microsoft 365:** Python, MSAL device-code login, delegated permissions (Calendars.ReadWrite, Mail.ReadWrite, Chat.Read, Tasks.ReadWrite, offline_access, User.Read, People.Read).
- **Updates:** scheduled delta polling with APScheduler.
- **Voice:** Pipecat + SmallWebRTC, faster-whisper for STT (Groq Whisper as fallback), Kokoro for TTS.
- **LLM:** Ollama qwen3 for anything with client data; Groq gpt-oss for speed on non-sensitive prompts.
- **Memory:** SQLite + sqlite-vec (or Chroma) with nomic-embed-text.
- **Calls:** Teams call and chat deep links.

## Paid upgrade path
- **LLM:** Claude Haiku 5.5 for triage and extraction; Sonnet 5.5 as the coordinator.
- **Speech:** Deepgram Nova-3 / Aura-2, or Azure Speech.
- **Teams bot:** Agents SDK + Agents Toolkit on Azure Bot Service F0.
- **Updates:** Graph webhooks.
- **Live calls:** ACS Call Automation, or an app-hosted media calling bot (C#).

## Could not verify
- **Protected APIs:** Microsoft's own documentation for the access-request process (the doc page returned 404).
- **Pricing:** Azure Speech pay-as-you-go rates.
- **Free tiers:**
  - Gemini's exact free quotas and model names.
  - Whether Groq's free tier supports tool calling, and Groq's data-retention terms.
  - Qdrant Cloud's free-tier size.
  - Microsoft 365 Business trial terms.
- **Calling:** what licensing a calling bot needs to dial phone numbers.
- **ACS Call Automation:** its support for two-way audio streaming into Teams interop calls from Python. This needs a check before the Phase 6 spike.
