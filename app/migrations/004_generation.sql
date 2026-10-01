CREATE TABLE generation_runs (
 job_id TEXT PRIMARY KEY REFERENCES jobs(id),
 provider TEXT NOT NULL, model TEXT NOT NULL, stage TEXT NOT NULL DEFAULT 'queued',
 max_output_tokens INTEGER NOT NULL, pricing TEXT NOT NULL,
 provider_response_id TEXT, usage TEXT, cost_usd TEXT,
 billing_status TEXT NOT NULL DEFAULT 'not_requested',
 started_at TEXT, completed_at TEXT, retry_of TEXT REFERENCES jobs(id)
);
