# Remote access (advanced)

For reaching DocuHive away from home. At home only, the [local network guide](local-network.md)
is simpler and needs none of this.

DocuHive has no second sign-in step yet, so do not put it on the open internet with a port
forward or a public address. This guide uses [Tailscale](https://tailscale.com), a private
network between your own devices: the app is reachable from your phone anywhere, and from
nobody else.

The production web service listens on `127.0.0.1:3000`. Internal API, database and converter
ports are not published. Install Tailscale on the host and on each phone or computer, enable
MagicDNS and HTTPS certificates for the tailnet, then on the host run:

```sh
tailscale serve --bg --https=443 http://127.0.0.1:3000
tailscale serve status
```

Open the resulting `https://…ts.net` address on your phone. Set that exact origin in
`DOCUHIVE_PUBLIC_URL` for both API and web, then recreate those services. Sign-in cookies,
CSRF validation, camera capture and service workers depend on the correct HTTPS address.
Do not point the phone at `localhost`: that is the phone itself.

Serve makes the app available to permitted members of your private tailnet. Use tailnet
access rules for the intended household devices. No router port-forwarding is needed.

The [Tailscale Serve reference](https://tailscale.com/docs/reference/tailscale-cli/serve)
and [HTTPS setup](https://tailscale.com/docs/features/tailscale-serve) describe the current
CLI and certificate flow. Verify the reported URL before configuring DocuHive.
