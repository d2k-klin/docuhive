# `apps/web/components/ui`

**Overview.** Design-system primitives (shadcn/ui, restyled to the DocuHive tokens). Every control shares one height and focus style.

## What's here

| Path | What it is |
| --- | --- |
| [`button.tsx`](button.tsx) | Button |
| [`input.tsx`](input.tsx) | Text input |

## Extending

Add primitives with the shadcn CLI, restyle them with `lib/ui/control.ts`, and add them to the `/dev/ui` kitchen sink so the height check covers them.
