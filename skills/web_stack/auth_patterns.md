# Authentication Patterns (Clerk / Auth.js / Supabase Auth)
Core concepts: session (proves who's logged in) vs authorization (what they're allowed to do) — keep these separate in your code.
JWT-based auth: tokens are signed, not encrypted — never put secrets in a JWT payload, only non-sensitive identity claims (user id, role).
Protect routes via middleware (check session before rendering/serving), not just hiding UI elements — client-side hiding is not security.
Password-based auth: always hash with bcrypt/argon2 server-side, never store or log plaintext passwords, even temporarily.
