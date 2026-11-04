# `config`

**Overview.** Public defaults for everything users can configure. Private settings live in your overlay folder (`DOCUHIVE_OVERLAY_DIR`), which overrides these files and is never committed.

## What's here

| Path | What it is |
| --- | --- |
| [`defaults/`](defaults/) | Default configuration files |

## Extending

Add a new defaults file under `defaults/`, load it with `docuhive.config.load_yaml`, and document every key with a comment.
