---
id: ADR-0021
status: accepted
date: 2026-05-14
---

# ADR-0021: Use Postgres as the job queue

## Context

Our background jobs run on Redis. Twice this year Redis lost jobs during a failover. Each loss meant a customer did not get an invoice. We need a queue that never drops a job.

We already run Postgres and know how to back it up. Adding a second system for queues has a real cost: another thing to patch, monitor, and explain to new hires.

## Decision

We will store jobs in a Postgres table and claim them with `SELECT ... FOR UPDATE SKIP LOCKED`. Workers poll every 500 ms.

```sql
SELECT id, payload FROM jobs WHERE status = 'pending' AND run_at <= now() ORDER BY run_at LIMIT 10 FOR UPDATE SKIP LOCKED;
```

A job is deleted only after it succeeds, so a crashed worker cannot lose it. Another worker picks it up after 60 seconds.

## Options we rejected

| Option | Why not |
|--------|---------|
| Keep Redis | It lost jobs twice |
| RabbitMQ | One more system to run |
| SQS | We would need to move off our own servers |

## Consequences

Good:

- Jobs survive failovers.
- We can enqueue a job in the same transaction as the data change.
- One less system to run.

Bad:

- Postgres handles about 2,000 jobs per second in our tests. We expect 200.
- Polling adds up to 500 ms of delay.
- Heavy queue traffic competes with normal queries.

If we pass 1,000 jobs per second, we will revisit this. The [load test results](https://example.com/wiki/engineering/adr/0021/load-test-results/2026-05) have the numbers.

## Follow-up

- `max_attempts` defaults to 5.
- Failed jobs move to the `dead_jobs` table.
- Alice will write the migration by the end of June.
