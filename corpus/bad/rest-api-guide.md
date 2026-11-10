# REST API Integration Guide

## Introduction

This guide is intended to provide developers with a comprehensive understanding of the API. The API offers robust capabilities and is designed to facilitate seamless integration with your existing systems, and by leveraging the endpoints described below you will be able to streamline your workflows.

## Authentication

Authentication is performed by means of bearer tokens. Tokens are issued by the identity service, tokens are validated by the gateway, and tokens expire after one hour. The API key rotation policy enforcement mechanism requires that keys be rotated every ninety days.

```bash
curl -X POST https://api.example.com/v2/orders -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"customer_id": "c_123", "items": [{"sku": "A-1", "qty": 2}], "utilize_cache": true}'
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v2/orders` | List orders |
| POST | `/v2/orders` | Create an order |
| DELETE | `/v2/orders/{id}` | Cancel an order |

## Request Parameters

The following parameters are accepted:

- customer_id
- `page_size`
- `sort_order`
- created_after

It is important to note that the `page_size` parameter has a maximum value of 100, and that requests exceeding this limit will result in a validation failure being returned to the caller with a status code of 422, along with a message that provides an indication of the offending field.

## Error Handling

Errors are returned in JSON. The error response schema definition document provides a description of every field. Clients should perform retries of failed requests in the case of a 503. A decision about backoff strategy should be made by the client, but exponential backoff is essential.

## Rate Limits

The service makes enforcement of rate limits per token. Limits are documented in the [rate limit reference](https://example.com/docs/api/v2/reference/rate-limits/overview/details). Exceeded limits will cause a 429 to be returned.

## In Summary

In summary, our API is a comprehensive and robust offering. We ensure that it will seamlessly facilitate your needs. Overall, we are crucially committed to your success.
