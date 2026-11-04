# Private HTTPS access

The production web service listens on `127.0.0.1:3000`. Internal API, database and converter
ports are not published. Use Tailscale on the host and phone, enable MagicDNS and HTTPS
certificates for the tailnet, then on the host run:

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
