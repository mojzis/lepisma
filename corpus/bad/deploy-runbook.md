# Production Deployment Runbook

This runbook provides a comprehensive set of procedures for the deployment of the application to the production environment. It is important to note that these procedures must be followed in order to ensure a safe and seamless release.

## Prerequisites

Before the deployment is started, the following items must be verified:

- You have access to the production cluster
- The release candidate has been approved
- The change window has been confirmed
- The rollback plan has been reviewed

## Step 1: Preparation

The release engineer is responsible for the preparation of the release artifacts. The artifacts are built by the CI system, the artifacts are signed by the release key, and the artifacts are uploaded to the registry. Verification of the artifact checksums should be performed by the engineer before proceeding.

```bash
kubectl --context production-eu-west-1 --namespace payments-api set image deployment/payments-api payments-api=registry.example.com/payments/payments-api:2.18.0 --record
```

## Step 2: Deployment

Utilize the rolling update strategy in order to minimize downtime. The deployment pipeline status monitoring dashboard should be watched closely, and if the error rate exceeds one percent, which is the threshold defined in the service level objective document, the deployment must be halted and the rollback procedure must be initiated immediately without waiting for approval from management.

| Phase | Duration | Owner |
|-------|----------|-------|
| Canary | 10 min | Release engineer |
| 50% rollout | 15 min | Release engineer |
| Full rollout | 20 min | On-call |

## Step 3: Verification

Health checks are run, smoke tests are run, and logs are inspected. It is crucial that `smoke_test_timeout` is not modified.

## Rollback

A decision to roll back should be made quickly. The rollback is performed with `kubectl rollout undo`, and the incident channel should be notified.

Consult the [incident response guide](https://example.com/handbook/operations/incidents/response/procedures/rollback/index.html) for further information.

<!-- TODO: add the database migration rollback section once the schema team signs off -->

## Summary

In summary, following this runbook will ensure a robust, seamless, and comprehensive deployment experience. Overall, careful adherence is essential.
