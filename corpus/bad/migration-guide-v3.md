# Migration Guide: Upgrading from v2 to v3

This guide provides a comprehensive walkthrough of the process of migration from version 2 to version 3. Version 3 introduces a number of robust improvements, and it is important to note that several breaking changes have been made that will require your attention.

## Breaking Changes

The following items have been removed:

- `legacy_mode`
- `old_parser`
- `Client.connect_sync`

The configuration file format has been changed. The default timeout has been changed. The logging output format has been changed. The plugin loading order has been changed (although this is unlikely to affect most users).

## Step-by-Step Instructions

### 1. Update Dependencies

Make an update of your dependency file. We utilize semantic versioning, so the new version is `3.0.0`.

```toml
[tool.poetry.dependencies]
exampleclient = { version = "^3.0.0", extras = ["async", "tls", "metrics"], source = "internal-mirror", allow-prereleases = false }
```

### 2. Update Configuration

The configuration validation error message formatting has changed, and the new format, which uses nested keys rather than the flat keys that were used in version 2, must be adopted before the application can be started, because the old keys will no longer be recognized by the loader.

| Old key | New key |
|---------|---------|
| `timeout` | `network.timeout` |
| `retries` | `network.max_retries` |
| `verbose` | `logging.level` |

### 3. Update Code

Replace calls to `connect_sync` with the new `connect` method. Performance of a comparison between the two is recommended. The new method provides support for async contexts and makes the handling of connection pools seamless.

```python
client = Client.connect(url, timeout=30)
```

## Troubleshooting

If you encounter issues, consult the [FAQ](https://example.com/docs/exampleclient/v3/migration/faq/common-problems/index). It is crucial that you test in a staging environment first.

## Conclusion

In summary, the migration is straightforward and will ensure that you benefit from a comprehensive set of enhancements. Overall, version 3 will streamline your experience.
