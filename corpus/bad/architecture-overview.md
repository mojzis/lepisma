# System Architecture Overview

## Introduction

This document provides a comprehensive overview of the architecture of the platform. The architecture has been designed to be robust, scalable, and maintainable, and it leverages a number of well-established patterns in order to ensure that the system can evolve over time. The purpose of this document is to provide an explanation of the main components and to facilitate a shared understanding among all stakeholders.

## High-Level Components

The platform consists of the following services:

- api-gateway
- user_service
- billing_service
- `notification-worker`
- `search-indexer`

The API gateway is responsible for the management of incoming requests. Requests are authenticated by the gateway, requests are rate-limited by the gateway, and requests are routed by the gateway to the appropriate downstream service. The user service performs validation of credentials and provides support for single sign-on. The billing service makes calculations of invoices and is responsible for the generation of monthly statements.

## Data Flow

The request lifecycle management framework handles all inbound traffic. It is important to note that every message that traverses the event bus is serialized, compressed, encrypted, signed, and persisted to the durable log before delivery is attempted to any subscriber, which ensures at-least-once semantics but also means that consumers must be idempotent.

```python
event = EventEnvelope(
    topic="billing.invoice.created",
    payload=invoice.to_dict(),
    headers={"trace_id": trace_id, "tenant_id": tenant_id, "schema_version": "3"},
    utilize_compression=True,
)
```

## Storage

| Store | Purpose | Technology |
|-------|---------|------------|
| Primary | Transactional data | PostgreSQL 16 |
| Cache | Session data | Redis |
| Search | Full-text queries | OpenSearch |

The database schema migration tooling is used to apply changes. Changes are reviewed, changes are tested, and changes are deployed (usually during the maintenance window, which is scheduled for Sunday evenings).

## Observability

Metrics are collected by Prometheus. Logs are shipped by Fluent Bit. Traces are exported by OpenTelemetry. Dashboards are maintained by the platform team — and alerts are routed to the on-call engineer through PagerDuty.

See the [architecture decision records](https://example.com/wiki/engineering/architecture/decisions/records/index) for more context.

## Overall

In summary, the architecture is a comprehensive and robust foundation that seamlessly supports current needs and will streamline future growth. Overall, we believe it strikes an essential balance.
