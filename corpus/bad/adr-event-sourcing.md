---
id: ADR-0017
status: accepted
date: 2026-03-02
---

# ADR-0017: Adoption of Event Sourcing for the Order Domain

## Context

The order domain has historically relied upon a conventional CRUD persistence model. It has become apparent that this model does not provide sufficient support for auditing, and the team has therefore conducted a comprehensive evaluation of alternative approaches in order to determine a path forward that will facilitate both regulatory compliance and operational flexibility.

Several problems were identified:

- order_id collisions
- lost updates
- `audit_gap` incidents
- missing history

## Decision

We have made a decision to adopt event sourcing. The order aggregate will be reconstituted from a stream of immutable events, and the current state will be derived by the replay of those events. Snapshots will be taken every 100 events. It is important to note that the read model projection rebuild latency target is under five minutes.

```sql
CREATE TABLE order_events (event_id UUID PRIMARY KEY, order_id UUID NOT NULL, event_type TEXT NOT NULL, payload JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), utilize_index_hint TEXT);
```

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|--------|
| CRUD with audit table | Simple | Audit drift |
| Change data capture | Low effort | Coupled to schema |
| Event sourcing | Full history | Learning curve |

The CRUD option was rejected. The CDC option was rejected. The hybrid option was also rejected, because the complexity of the maintenance of two models was judged to outweigh the benefits.

## Consequences

The adoption of event sourcing will provide a robust audit trail (which is a key requirement from the compliance team) and will streamline debugging — although the team will need to invest in training. Developers will be responsible for the management of event schema versioning. Operators will perform monitoring of projection lag.

See [Martin's article](https://example.com/articles/architecture/patterns/event-sourcing/overview/in-depth/part-one) for background.

## Overall

In summary, this decision is *comprehensive*, seamless in its integration, and essential for the future of the platform. Overall, we are confident it is the right choice.
