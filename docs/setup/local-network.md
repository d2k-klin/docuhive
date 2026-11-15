# Use DocuHive on your home network

The easy option: every phone, tablet and computer on your home Wi-Fi or cable network opens
DocuHive over HTTPS. No account with another service and no app on your devices. Nothing is
reachable from outside the house; for that, see [remote access](remote-access.md).

## 1. Pick the address

Your devices need one address for the machine that runs DocuHive. Use either:

- its **name**, if your router gives it one, such as `docuhive.fritz.box` or `myserver.local`; or
- its **number**, such as `192.168.1.20`. Tell your router to always give this machine the same
  number (routers call this a fixed or reserved address).

Check it from another device: `ping docuhive.fritz.box`.

## 2. Switch it on

Add two lines to `.env.production`, with your address in both:

```dotenv
DOCUHIVE_LAN_HOST=docuhive.fritz.box
DOCUHIVE_PUBLIC_URL=https://docuhive.fritz.box
```

Start DocuHive with the home-network option:

```bash
make up PROD_ENV=.env.production LAN=1
```

Use `LAN=1` every time you run `make up`, `make down` or `make logs`. If the host has a
firewall, allow ports 80 and 443 from your home network only.

Open `https://docuhive.fritz.box` on any device at home and sign in.

## 3. Trust the certificate, once per device

DocuHive makes its own certificate, because a home address cannot get a public one. Until a
device trusts it, the browser shows a warning, and **phone capture does not work**.

On each device, open `http://docuhive.fritz.box/docuhive-root.crt` (plain `http`) to download
the certificate, then:

| Device | What to do |
| --- | --- |
| iPhone, iPad | Open the downloaded profile in **Settings** and install it. Then **Settings → General → About → Certificate Trust Settings**: switch it on. |
| Android | **Settings → Security → Encryption & credentials → Install a certificate → CA certificate**, and pick the file. |
| Mac | Open the file, add it to the **login** keychain, open it there and set **Trust** to **Always Trust**. |
| Windows | Open the file, **Install Certificate → Local Machine → Trusted Root Certification Authorities**. |
| Linux | Copy it to `/usr/local/share/ca-certificates/` and run `sudo update-ca-certificates`; Firefox has its own list under **Settings → Certificates**. |

Reopen the browser afterwards. The certificate only vouches for your DocuHive: keep it within
the household or the office.

## What to know

- **Who can reach it.** Every device on your network sees the sign-in page; nobody gets further
  without an account. Keep guests on the router's guest network.
- **Do not forward ports** on your router to this machine. DocuHive has no second sign-in step
  yet, so it does not belong on the open internet.
- **The certificate authority** lives in the `lan-authority` Docker volume. If you delete that
  volume, DocuHive makes a new one and every device has to trust the new certificate.
- **If the address changes,** update both lines in `.env.production` and run `make up` again.
- **Away from home** you cannot reach it this way. Add [remote access](remote-access.md) when
  you need that; both can run at once only if they share the same address, so pick one address
  for `DOCUHIVE_PUBLIC_URL`.
