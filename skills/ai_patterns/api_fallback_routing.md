# Multi-API Fallback Routing
Pattern: try primary API (e.g. Groq) -> on failure (auth, rate limit, timeout) -> try secondary (NVIDIA NIM, DeepSeek) -> log which provider actually responded.
Best practice: classify failure type before retrying — auth errors won't be fixed by retrying the same provider, only by switching providers or fixing the key.
Avoid: silently swallowing errors with no visible log — always surface which provider failed and why, even briefly, for debuggability.
