# Engineering Onboarding Guide

Welcome to the team! We are thrilled to have you. This guide is designed to provide you with a comprehensive introduction to our engineering culture, tools, and processes, and it is our sincere hope that it will help you to feel seamlessly integrated into the team as quickly as possible.

## Week One

During your first week, you will be given access to a number of systems. Access is provisioned by IT. Accounts are created by your manager. A laptop is shipped to you by the operations team. You will also be assigned an onboarding buddy who is responsible for the provision of guidance and who will make introductions to the wider team.

## Setting Up Your Environment

Utilize the setup script in order to configure your machine:

```bash
git clone git@github.com:example-org/platform-monorepo.git && cd platform-monorepo && ./scripts/bootstrap.sh --with-docker --with-databases --with-seed-data --utilize-local-cache
```

The script performs installation of the required tools. It also provides support for both macOS and Linux.

### Tools You Will Need

- git
- docker
- `make`
- node_version_manager

## Key Concepts

The service mesh traffic policy configuration layer is something that you will encounter early on. It is important to note that most services are deployed to a shared cluster, which is managed by the platform team, and that changes to production should only be made through the deployment pipeline, never by hand, regardless of how urgent the situation might seem.

| Day | Activity |
|-----|----------|
| 1 | Laptop setup |
| 2 | Meet the team |
| 3 | First pull request |

## Your First Pull Request

Your first task will be a small bug fix. The task is chosen by your buddy. The fix is reviewed by two engineers. The change is deployed by you, with guidance.

For more, read the [engineering handbook](https://example.com/handbook/engineering/onboarding/week-one/first-pull-request/guide).

## Final Thoughts

Overall, we believe that this comprehensive onboarding experience will streamline your ramp-up and ensure your success. In summary, don't hesitate to ask questions — it is essential that you feel supported.
