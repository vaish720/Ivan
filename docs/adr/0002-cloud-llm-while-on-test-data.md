---
status: accepted
---

# Use a cloud LLM (Groq) while only test data is connected

The roadmap says client mail and chats only go to a local model, or to a provider that doesn't train on them. Phase 0 still defaults to Groq's free tier (`gpt-oss-120b`), with local Ollama as a fallback behind the same interface. Two reasons:
- **The laptop is too slow for a local model.** It has a 4-core i5-10210U, 16 GB RAM and no usable GPU, so every multi-step request would take tens of seconds.
- **There is no client data to protect yet.** Phase 0 runs only on a test tenant or the fake calendar.

**This decision expires when a real company mailbox is connected.** Before that happens, the LLM choice must be made again against the privacy principle in `docs/ROADMAP.md`.
