# Capture from a phone, scanner or script

Open `/capture` to photograph pages or choose images and PDFs. Images are oriented from
EXIF, reduced to a 2400-pixel long edge and converted to JPEG before upload. Use Earlier,
Later or drag to change page order; Rotate turns a photo clockwise. Multiple photos are
one document by default. PDFs and uncombined pages are submitted separately.

Captures go through the same `ingest.submit` intake as email and web uploads. While the
server can't be reached, uploads stay queued; no success is shown until it accepts them.

## Install on your phone

1. Follow [remote access](remote-access.md) to open the HTTPS address on your phone.
2. Sign in, return to `/capture`, and wait for the initial page to finish loading.
3. iPhone: Safari → Share → Add to Home Screen. Android: Chrome → menu → Install app.
4. Capture three pages, reorder them, then choose **Upload document**. Keep the original
   photos until the processing result says the document is stored.

Only the capture shell and its static assets are cached. Document lists, previews and API
responses are never cached by the service worker. Pending files live in this browser's
IndexedDB and are tied to the account that saved them. Switching accounts cannot send
another person's queue. A queued upload also checks its expected owner at the API.

Offline: keep the page open, or reopen the installed app after its first online visit.
Choose **Save to upload when online**. Reconnect and open capture to finish. Chrome may
retry in the background; iPhone needs the app opened. Retries back off, and unsupported or
oversized files stay visible with a next step. Removing a queued item requires confirmation.
Browser storage is device-local and may be cleared by the browser; keep original photos.

## Scanner folder

The OCR worker polls every 30 seconds; it uses no filesystem notification service.

- Default path: the vault's `consume` folder (it follows the vault chosen on Storage health). Set `DOCUHIVE_CONSUME_DIR` to an existing
  alternative share. A blank value means the default, never the current directory.
- `consume/<username>/scan.pdf` belongs to that active user. Loose files belong to
  `DOCUHIVE_CONSUME_DEFAULT_OWNER`; without it, loose files are ignored.
- Dotfiles, Office temporary files, `.part`, `.tmp`, `.crdownload`, `Thumbs.db` and symbolic
  links are ignored. Unknown users and disabled accounts are ignored.
- Files must have the same size, modification time and inode across two polls. The ledger
  is durable, so restarting a worker does not bypass the stability check.
- Pickup copies, fsyncs and verifies the file onto SSD staging, then calls `ingest.submit`.
  The scanner original stays in place until the document is stored and the vault original
  has the same checksum. A quarantined document leaves its scanner copy intact.
- Rejected input moves into `consume/_rejected/` with a reason sidecar. Correct the problem
  and move the file back to retry. Files are never picked up while the vault ID is missing
  or differs from the database's registered ID.

Give each scanner permission only to its own folder. In production the default folder is
inside the NAS mount; an alternative host path also needs an explicit Compose bind mount.

## Personal token upload

In **API tokens**, create a token with **Upload documents** only. Store it in your script's
secret store. Send multipart files to the browser-facing address:

```sh
curl --fail-with-body \
  -H "Authorization: Bearer $DOCUHIVE_UPLOAD_TOKEN" \
  -F 'files=@letter.pdf' \
  'https://your-host.your-tailnet.ts.net/api/upload'
```

For several images in one document, repeat `-F 'files=@page.jpg'` and add `?combine=true`.
An upload-only token cannot read documents or list your archive. Its owner is always the
signed-in token owner; token uploads are recorded as source `api`. Browser capture uses
source `mobile`. Both use the same processing pipeline. The configured upload limit applies
to all files together and is enforced for chunked requests as well as normal multipart.

## Phone acceptance checklist

Record device/browser versions and actual results; desktop emulation is insufficient.

- iPhone over Tailscale away from home: three photos, one with EXIF rotation → reorder →
  one correctly oriented, searchable three-page PDF.
- iPhone: first online visit → airplane mode → capture → close/reopen → reconnect/open →
  accepted once, queued bytes removed only after acceptance.
- Android Chrome: repeat online/offline checks, including background retry.
- Expired session: files stay queued; sign in as the same user and retry.
- Another account: old queue stays unsent. Sign back in to its owner and finish.
- Scanner: keep writing a file across polls → no pickup; finish → pickup; disconnect NAS
  during processing → source retained; recover → verify stored original then release source.

These hardware checks remain pending until real intake and the target phone/NAS are available.
