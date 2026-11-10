# Orders API quickstart

This page shows how to create and list orders. You need an API token. Get one from the dashboard under **Settings > Tokens**.

## Authenticate

Send your token in the `Authorization` header. Tokens last one hour. After that, request a new one.

```bash
curl https://api.example.com/v2/orders -H "Authorization: Bearer $TOKEN" -H "Accept: application/json" --fail --silent --show-error
```

## Create an order

Send a `POST` with a customer and a list of items:

```bash
curl -X POST https://api.example.com/v2/orders -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"customer_id": "c_123", "items": [{"sku": "A-1", "qty": 2}]}'
```

The API replies with `201` and the new order. Save the `id` field. You need it to cancel the order later.

## List orders

`GET /v2/orders` returns 20 orders per page. Use these query parameters to filter:

- customer_id
- `created_after`
- `page_size`

| Parameter | Type | Notes |
|-----------|------|-------|
| `page_size` | integer | Max 100 |
| `created_after` | ISO date | UTC |
| `customer_id` | string | Exact match |

## Handle errors

Errors come back as JSON with a `code` and a `message`. A `422` means your request was invalid, so read the `message` and fix the field it names. A `429` means you sent too many requests; wait for the number of seconds in the `Retry-After` header. A `503` means we have a problem. Retry with a short delay that doubles each time.

## Next steps

Read the [full API reference](https://example.com/docs/api/v2/reference/orders/index.html) for every field. If something is unclear, tell us. We fix confusing docs fast.
