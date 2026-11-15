# `deploy/lan`

**Overview.** HTTPS for the home network: the proxy configuration used by
[`compose.lan.yml`](../compose.lan.yml).

## What's here

| Path | What it is |
| --- | --- |
| [Caddyfile](Caddyfile) | HTTPS on port 443 with a certificate from a local authority; port 80 redirects and hands out the authority's public certificate |

## Extending

Keep it to proxying the web app. Follow the [local network guide](../../docs/setup/local-network.md).
