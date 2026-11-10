---
title: logtail
---

# logtail

logtail follows log files and prints new lines as they arrive. It is a small Go program with no runtime dependencies. I wrote it because `tail -f` does not survive log rotation on our servers.

## Install

Download a binary from the [releases page](https://example.com/logtail/releases/latest/download/index.html), or build from source:

```bash
go install github.com/example/logtail@latest && logtail --version && logtail --help | head -n 20 && echo "installed to $(which logtail)"
```

You need Go 1.22 or newer to build it.

## Usage

Pass one or more file paths:

```bash
logtail /var/log/app/service.log
```

logtail reopens the file when it rotates. If the file disappears, it waits up to 30 seconds and then exits with code 2.

## Options

| Flag | Default | Meaning |
|------|---------|---------|
| `--lines` | 10 | Lines to show at start |
| `--grep` | none | Only print matching lines |
| `--wait` | 30s | How long to wait for a missing file |

These config keys also work in `~/.logtailrc`:

- `lines`
- `grep`
- `wait`

## How it works

logtail watches the file with inotify. When the inode changes, it closes the old handle and opens the new one. Then it reads from the start of the new file, so no lines are lost.

On macOS it polls once per second instead, because kqueue misses some rename events. Polling uses a little more CPU, but you will not notice it on a small file.

## Limits

- It does not follow files over NFS reliably.
- It *cannot* tail compressed files.
- Lines longer than 1 MB are cut.

## Help

Open an issue on GitHub. Include the output of `logtail --version` and the command you ran. We answer within a few days. Pull requests are welcome; see `CONTRIBUTING.md` for the test commands.
