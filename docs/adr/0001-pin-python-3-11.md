# Pin Python 3.11, not the installed 3.14

The laptop has only Python 3.14. We pin the project to Python 3.11, managed by `uv`. The reason is the Microsoft 365 Agents SDK, which the Teams bot needs in Phase 5: it supports Python 3.9–3.11 only ([overview](https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/agents-sdk-overview)). Voice libraries (faster-whisper, Kokoro, Pipecat) also tend to trail the newest Python release. Revisit when the Agents SDK supports a newer version.
