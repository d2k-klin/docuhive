# `services/docuhive/src/docuhive/notify`

**Overview.** Notifications to ntfy or email, and the periodic checks that trigger them.

## What's here

| Path | What it is |
| --- | --- |
| [`__init__.py`](__init__.py) | Notifications: fan out to a user's channels |
| [`jobs.py`](jobs.py) | Periodic notification triggers: dead jobs, review backlog, backup age |
| [`models.py`](models.py) | notification_channels + notification_log |
| [`routes.py`](routes.py) | /api/notifications: channels (encrypted config), test send, log, setup status |

## Extending

Add a channel as a plugin; messages carry titles and links only, never document content.
