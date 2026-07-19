# Supabase Patterns
Supabase = Postgres database + auth + storage + realtime, accessed via a client library (supabase-js).
Typical setup: create a client with project URL + anon key, use Row Level Security (RLS) policies on every table to control who can read/write — never disable RLS in production.
Auth flow: supabase.auth.signUp / signInWithPassword for email/password, or signInWithOAuth for social login. Session is managed automatically by the client.
Database queries: supabase.from('table').select() / insert() / update() / delete() — these return { data, error }, always check error before using data.
