# `assets/brand`

**Overview.** The Mr.D brand files DocuHive uses: the mascot in the README and, as the UI grows, in the sidebar and empty states. They come from the Mr.D brand archive (the same set ReelHive ships) and are committed here, so nothing is loaded from a server. **They are not covered by the code licence** (see [`LICENSE.md`](LICENSE.md)); forks keep the code and replace these files.

## What's here

| File | Used for |
| --- | --- |
| `mr-d-art-9.webp` (+ `@2x`) | Inspecting a document checklist: the README hero, the review queue |
| `mr-d-laptop.webp` (+ `@2x`) | Default mascot: sidebar footer, sign-in |
| `mr-d-art-3.webp` (+ `@2x`) | Walking: first launch and the setup wizard |
| `mr-d-art-5.webp` (+ `@2x`) | Working: processing and long-running jobs |
| `mr-d-art-7.webp` (+ `@2x`) | Presenting: answers, finished analyses |
| [`manifest.json`](manifest.json) | Every file with its SHA-256 and its source in the archive |
| [`LICENSE.md`](LICENSE.md) | The brand licence |

## Rules

- Never edit these files by hand. Updates come from Dav as a new set with a new `manifest.json`.
- Every file must match its SHA-256 in the manifest, and the whole set stays under 2 MB.
- Originals and masters stay in the private brand archive, not in this repo.

## Extending

New poses (for example Mr.D with a scanner or a mailbox) are made from the brand archive and come back here as a new set with an updated manifest. Reference them from the UI by relative path; never hot-link images from elsewhere.
