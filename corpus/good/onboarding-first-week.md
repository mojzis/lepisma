# Your first week

Welcome. This page tells you what to do on each day. You do not need to finish everything. Ask your buddy when you are stuck.

## Day 1: Get set up

IT ships your laptop before you start. Your manager creates your accounts. If something does not work by 10:00, message `#it-help`.

Then clone the monorepo and run the setup script:

```bash
git clone git@github.com:example-org/platform-monorepo.git && cd platform-monorepo && ./scripts/bootstrap.sh --with-docker --with-databases --with-seed-data
```

The script installs everything you need. It takes about 20 minutes, so get coffee.

You will use these tools every day:

- git
- docker
- `make`
- fnm

## Day 2: Meet people

Your buddy will introduce you to the team. Book a 30-minute chat with each of these people:

| Person | Topic |
|--------|-------|
| Your manager | Goals for the first quarter |
| Your buddy | How we work |
| Platform lead | How deploys work |

## Day 3: Fix a small bug

Your buddy picks a bug for you. It is small on purpose. Open a pull request by the end of the day. Two people review it, and they will leave comments. Comments are not criticism. They are how we all learn the code.

## Day 4 and 5: Ship it

Merge your pull request after both approvals. Then deploy it yourself with your buddy next to you. The [deploy guide](https://example.com/handbook/engineering/deploys/how-to/step-by-step/index.html) lists each step.

*Never* change production by hand. Always use the pipeline, even when you are in a hurry.

## Questions

Nobody expects you to know everything yet. Ask in `#dev-help`. People answer fast, and no question is too basic.
