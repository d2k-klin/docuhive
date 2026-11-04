# `apps/web/lib/capture`

**Overview.** Browser-only image preparation for phone capture.

## What's here

| Path | What it is |
| --- | --- |
| [images.ts](images.ts) | EXIF-aware downscaling, rotation and immutable page ordering |

## Extending

Keep the long edge bounded, preserve orientation and test image transforms with a mocked canvas.
