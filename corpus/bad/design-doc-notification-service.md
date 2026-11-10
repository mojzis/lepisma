# Design Document: Notification Service

**Author:** Platform Team
**Status:** Draft

## Abstract

This design document presents a comprehensive proposal for the creation of a unified notification service that will leverage existing infrastructure in order to deliver email, SMS, and push messages in a robust, reliable, and seamless manner, thereby facilitating a consistent user experience across all of our products and ensuring that the engineering effort currently duplicated across teams is eliminated.

## Goals

- Reduce duplicate code
- Improve delivery rates
- Support `email`, `sms`, and `push`
- user_preferences enforcement

## Non-Goals

Marketing campaign management is not in scope. Analytics is not in scope. Template editing is not in scope.

## Proposed Design

The service will be responsible for the management of message queues. Messages will be accepted by the API, messages will be validated by the router, and messages will be dispatched by the channel workers. The delivery retry scheduling logic implementation will make use of exponential backoff. The service provides support for templating and performs validation of recipient addresses.

```yaml
channels:
  email: {provider: ses, region: eu-west-1, max_retries: 5, backoff_seconds: [1, 5, 30, 120, 600], utilize_batching: true, batch_size: 50}
```

### Data Model

| Table | Key columns |
|-------|-------------|
| `messages` | id, channel, status |
| `preferences` | user_id, channel, opted_in |

It is important to note that preferences must be checked prior to every send, and that failure to perform this check may result in a violation of privacy regulations, which is a crucial concern that has been raised by the legal team and which the design addresses through a mandatory middleware layer.

## Risks

A decision on the provider has not been made. Capacity estimates need to be refined. See the [capacity spreadsheet](https://example.com/sheets/platform/notification/capacity/estimates/2026/q1).

## Open Questions

- Should we utilize a managed queue?
- Who owns on-call?

## Overall

In summary, this proposal is a comprehensive and essential step that will streamline our messaging. Overall, we recommend approval.
