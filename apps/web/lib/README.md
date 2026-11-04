# `apps/web/lib`

**Overview.** Shared web helpers: the typed API client, the proxy rules, navigation, auth helpers, UI strings and control classes.

## What's here

| Path | What it is |
| --- | --- |
| [`api/`](api/) | The typed API client |
| [`i18n/`](i18n/) | User-facing copy: UI strings and the error messages that tell people what happened and what to do |
| [`ui/`](ui/) | The shared control class that gives every input, select and button the same height, border and focus ring |
| [`auth.ts`](auth.ts) | Session and redirect helpers |
| [`nav.ts`](nav.ts) | Navigation entries |
| [`proxy.ts`](proxy.ts) | Proxy rules: which headers reach the API, and streaming without buffering |
| [`utils.ts`](utils.ts) | Class-name helper |
| [capture/](capture/) | EXIF-aware image preparation and page ordering |

## Extending

Keep helpers framework-light and covered by a unit test in `../tests`.
