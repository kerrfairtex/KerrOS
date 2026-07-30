-- kernel/decision_log_schema.sql
-- Append-only event log for scope, deploy, verification, and watchdog events.
-- WAL mode enabled at connection time for concurrent writers.
-- Tamper-evidence: prev_hash / entry_hash SHA-256 chain (ADR-017).

CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    actor TEXT NOT NULL,
    decision_type TEXT NOT NULL,
    input_summary TEXT NOT NULL,
    outcome TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    prev_hash TEXT NOT NULL DEFAULT '',
    entry_hash TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_decisions_timestamp ON decisions(timestamp);
CREATE INDEX IF NOT EXISTS idx_decisions_type ON decisions(decision_type);
