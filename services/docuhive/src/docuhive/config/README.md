# `services/docuhive/src/docuhive/config`

**Overview.** Settings, the private overlay, versioned prompts and plugin discovery.

## What's here

| Path | What it is |
| --- | --- |
| [`__init__.py`](__init__.py) | Public configuration contract: defaults, private overlays and plugin hooks |
| [`settings.py`](settings.py) | Validated core runtime settings |

## Extending

New settings go into the settings class of the module that owns them, with a documented default in `.env.example`.

`get_setting` and `set_setting` store validated non-secret runtime preferences in the settings table. They are uncached so API and worker processes see category changes immediately; the owning API enforces permissions.
