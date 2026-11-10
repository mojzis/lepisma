# Fixing slow builds

If your build takes more than five minutes, work through this list. Most slow builds have one of three causes.

## 1. The cache is cold

First, check whether the cache is hit. Run:

```bash
make build VERBOSE=1 2>&1 | grep -E "cache (hit|miss)" | sort | uniq -c | sort -rn | head -n 20 && echo "Look for a high miss count on the dependency layer"
```

If you see many misses, you probably changed `package-lock.json` or the base image. That is normal once. If it happens on every build, the cache key is wrong.

To fix it, clear the local cache and rebuild:

```bash
make clean-cache && make build
```

## 2. Tests run in series

By default, tests run one at a time on laptops. Turn on parallel runs with the `--workers` flag. Four workers is a good start.

| Workers | Typical time |
|---------|--------------|
| 1 | 9 min |
| 4 | 3 min |
| 8 | 2 min |

More workers do not always help. Past eight, the database becomes the bottleneck.

## 3. Docker is out of memory

Docker Desktop defaults to 2 GB. Our build needs 6 GB. Open the settings, raise the limit, and restart Docker. You will know this is the problem when you see `Killed` in the output.

## Still slow?

Collect these values before you ask for help:

- build_id
- `git rev-parse HEAD`
- the output of `make doctor`

Post them in `#dev-help`. The [build dashboard](https://example.com/grafana/d/builds/ci-duration?orgId=1&var-branch=main&from=now-7d) also shows whether the whole CI fleet is slow, which is a different problem and not your fault.

Do not skip tests to save time. Ensure the suite passes locally before you push, or CI will fail later and cost everyone more.
