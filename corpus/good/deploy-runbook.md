# Deploying payments-api

Use this runbook to ship a release to production. A full deploy takes about 45 minutes. Do not start one after 16:00 on Fridays.

## Before you start

Check that:

- you can run `kubectl` against the production cluster
- the release has two approvals
- the on-call engineer knows you are deploying

## Step 1: Build and push

CI builds the image when you tag a release. Wait for the green check on the tag, then confirm the image exists:

```bash
docker manifest inspect registry.example.com/payments/payments-api:2.18.0 > /dev/null && echo "image found" || echo "image missing, check the CI run"
```

## Step 2: Canary

Send 5% of traffic to the new version:

```bash
kubectl --context production-eu-west-1 argo rollouts set image payments-api payments-api=registry.example.com/payments/payments-api:2.18.0
```

Watch the error rate on the [payments dashboard](https://example.com/grafana/d/payments/overview?orgId=1&refresh=30s). If it goes above 1%, abort and roll back.

## Step 3: Full rollout

| Stage | Traffic | Wait |
|-------|---------|------|
| Canary | 5% | 10 min |
| Half | 50% | 15 min |
| Full | 100% | 20 min |

Promote each stage with `kubectl argo rollouts promote payments-api`. Check the logs between stages. Look for `ERROR` lines you have not seen before.

## Roll back

Run `kubectl argo rollouts undo payments-api`. It takes about two minutes. Then post in `#incidents` and tell the on-call engineer what you saw.

Never edit `smoke_test_timeout` during a deploy. The smoke tests depend on it.

## After the deploy

Close the release ticket. Write down anything odd in the release notes, even if it seems small. The next person will thank you.

<!-- Last reviewed by the payments team in October. -->
