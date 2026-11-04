---
name: docuhive-ui
description: "Build or change any DocuHive web screen or component (Next.js App Router, Tailwind, shadcn/ui): design tokens, the standard font, the restrained type scale, uniform control heights for inputs/selects/date fields/checkboxes/buttons, spacing and alignment rules, tables, forms, dialogs, empty/loading/error states, dark mode and accessibility. Use whenever you touch apps/web, add a page, style a control, or review UI for alignment."
---

# DocuHive UI design system

DocuHive is a calm, dense, modern tool that people use every day. The UI must look like **one product**: one font, a small type scale, and every control at the same height on the same grid. This skill is the source of truth; `apps/web/app/globals.css` and `apps/web/lib/ui/` implement it.

## Procedure

1. Read `apps/web/app/globals.css` (tokens), `apps/web/lib/ui/control.ts` (shared control classes) and the nearest existing page before writing anything.
2. Build with the existing `components/ui/*` primitives. If one is missing, add it with the shadcn CLI, then **restyle it to the tokens below** before using it. Never paste raw shadcn defaults.
3. Never hard-code colours, font sizes, heights or radii in a component. Use the tokens and Tailwind utilities mapped to them.
4. Lay out with the page template (below). Check the screen at 375 px, 768 px and 1280 px, in light and dark.
5. Open `/dev/ui` (the kitchen-sink page, dev only) and make sure any new control appears there, next to the others.
6. Run `make test-ui` (Playwright + axe + the control-height check) before you open the PR.

## Tokens (`app/globals.css`)

```css
:root {
  /* Font: Inter, self-hosted at build time via next/font (no runtime Google requests) */
  --font-sans: var(--font-inter), ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
  --font-mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;

  /* Type scale: small on purpose. Nothing in the app is bigger than --text-xl. */
  --text-xs: 0.75rem;    /* 12px  help text, badges, table meta      */
  --text-sm: 0.8125rem;  /* 13px  labels, secondary text             */
  --text-base: 0.875rem; /* 14px  body, inputs, buttons, table cells */
  --text-md: 1rem;       /* 16px  section titles (h2), dialog titles */
  --text-lg: 1.125rem;   /* 18px  card titles on the dashboard only  */
  --text-xl: 1.25rem;    /* 20px  page title (h1), the maximum       */

  /* Controls: one height for everything you can type in, pick or click */
  --control-h: 2.25rem;     /* 36px default */
  --control-h-sm: 2rem;     /* 32px dense toolbars, table row actions */
  --control-h-lg: 2.5rem;   /* 40px mobile primary actions only */
  --control-px: 0.75rem;    /* 12px horizontal padding */
  --radius: 0.5rem;         /* 8px controls */
  --radius-card: 0.75rem;   /* 12px cards, dialogs */
  --check-size: 1rem;       /* 16px checkbox / radio */

  /* Colour (light) — semantic names only */
  --bg: #f7f8fa;  --surface: #ffffff;  --surface-2: #f1f3f6;
  --border: #e2e5ea;  --border-strong: #c9ced6;
  --text: #15181d;  --text-muted: #5b6472;  --text-subtle: #8a93a1;
  --primary: #2f5bea;  --primary-hover: #2549c4;  --primary-fg: #ffffff;
  --success: #138a52;  --warning: #b26b00;  --danger: #c8312b;  --info: #2f6fb8;
  --focus-ring: #2f5bea66;
}
:root.dark {
  --bg: #0f1115;  --surface: #161920;  --surface-2: #1d212a;
  --border: #2a2f3a;  --border-strong: #3a4150;
  --text: #e8eaee;  --text-muted: #a2aab7;  --text-subtle: #747d8c;
  --primary: #5b82ff;  --primary-hover: #7898ff;  --primary-fg: #0b0d12;
  --success: #34c27f;  --warning: #e0a02e;  --danger: #f06a63;  --info: #5ea2ef;
  --focus-ring: #5b82ff80;
}
html { font-family: var(--font-sans); font-size: 16px; }
body { background: var(--bg); color: var(--text); font-size: var(--text-base); line-height: 1.5;
       -webkit-font-smoothing: antialiased; font-feature-settings: "cv11", "ss01"; }
.tabular { font-variant-numeric: tabular-nums; }
```
Map the tokens in `tailwind.config.ts` (`fontSize.xs…xl`, `height.control`, `height.control-sm`, `height.control-lg`, `borderRadius.DEFAULT/card`, and the colours via `rgb(var(--…))` or direct CSS vars). Theme: `class` strategy on `<html>`, defaulting to `prefers-color-scheme`, with a toggle in the user menu.

## Typography rules

| Element | Size | Weight | Notes |
|---------|------|--------|-------|
| Page title `h1` | `--text-xl` (20px) | 600 | one per page, in the page header |
| Section title `h2` | `--text-md` (16px) | 600 | |
| Sub-section `h3` | `--text-base` (14px) | 600 | |
| Body, inputs, buttons, cells | `--text-base` (14px) | 400 (buttons 500) | |
| Labels | `--text-sm` (13px) | 500 | |
| Help, meta, badges | `--text-xs` (12px) | 400–500 | `--text-muted` |

- **No huge titles.** No `text-2xl` or bigger anywhere in the app. The single exception is the login screen wordmark (24px).
- Sentence case everywhere ("Upload documents", not "Upload Documents"). No all-caps, except tiny table headers (12px, 500, letter-spacing 0.02em).
- Numbers in tables, amounts and dates use `.tabular`. Amounts are right-aligned.
- Line length in prose (help, AI answers) is at most `65ch`.

## Controls: they must all look alike

`lib/ui/control.ts` exports **one** base class string, used by Input, Textarea, SelectTrigger, Combobox trigger, DateInput, Search, the TagInput container and the file-picker button:

```ts
export const control =
  "h-control w-full rounded border border-[var(--border)] bg-[var(--surface)] px-[var(--control-px)] " +
  "text-[length:var(--text-base)] text-[var(--text)] placeholder:text-[var(--text-subtle)] " +
  "transition-colors hover:border-[var(--border-strong)] " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] focus-visible:border-[var(--primary)] " +
  "disabled:cursor-not-allowed disabled:opacity-50 aria-[invalid=true]:border-[var(--danger)]";
export const controlSm = control.replace("h-control", "h-control-sm");
```

| Control | Spec |
|---------|------|
| Text input, search, number | `control`, 36px. Leading icon 16px at 12px from the left, with the text indent at 36px |
| Select / dropdown (Radix Select) | the trigger uses `control` plus a chevron 16px on the right. Menu items are 32px tall, padded 8px/12px, and the menu matches the trigger width |
| Combobox (correspondent, category tree) | same trigger as Select. Typeahead list items are 32px, and the "Create …" item comes last with a `+` icon |
| Date | native `<input type="date">` with `control` and `color-scheme` set for dark mode. **No date-picker library** |
| Textarea | `control` minus the fixed height: `min-h-[5.5rem] py-2`, vertical resize only |
| Tag input | a container with `control` and `min-h` (not a fixed `h`) that wraps. Chips are 24px tall, 12px text, radius 6px |
| Button | 36px tall, `px-3.5`, 14px weight 500, radius 8px. Variants: `primary`, `secondary` (surface + border), `ghost`, `danger`. Icon + label gap is 8px. **Icon-only buttons are 36×36** with an `aria-label` |
| Checkbox / radio | 16px box, radius 4px (radio full), with the label at 14px and a 8px gap. The row is 20px tall and vertically centred. The click target is the whole label |
| Switch | 20×36 track, for on/off settings that apply immediately. A checkbox is for choices that are submitted with a form |
| Badge / status | 20px tall, `px-2`, 12px weight 500, radius 6px. **Status always pairs colour + icon + text** |
| File drop zone | dashed `--border-strong` with radius-card, at least 120px tall, centred icon + one line + a "Choose files" secondary button |

**Height check:** the `/dev/ui` page renders every control in one row inside `[data-testid="control-row"]`. `tests/ui/controls.spec.ts` asserts that all of them have the same `boundingBox().height` (36 ± 0.5 px) and the same top y. Any new control must be added there.

## Spacing & alignment

- **4px grid.** Use only the Tailwind steps `1 2 3 4 5 6 8 10 12` (4–48px). No arbitrary pixel margins.
- Page padding is 24px on desktop and 16px under 768px. Content max width is 1280px; reading pages (help, chat) are 760px.
- **Page header:** a single row with the title and a one-line description (`--text-muted`, 13px) on the left, and actions on the right, all vertically centred. On mobile the actions wrap below. Leave 24px between the header and the content.
- **Forms:**
  - The label sits above the field, 6px gap. Help text goes below it, 4px gap, at 12px muted. The inline error replaces the help text, in `--danger` with an icon.
  - 16px between fields, and 24px plus a 13px h3 between groups.
  - Two-column forms only from 1024px up. Both columns share the label row, so the fields line up.
- **Toolbars and filter bars:** every item is a control of the same height (36px, or `sm` 32px for the whole bar), with an 8px gap and wrapping on mobile. Never mix heights in one row.
- **Dialogs:**
  - width 480px (forms) or 720px (previews), padding 24px
  - title 16px/600, then the body
  - the footer is right-aligned (secondary then primary), with 8px between the buttons
  - destructive actions use `danger` and name the consequence ("Move 12 documents to trash")
- **Tables:**
  - header 36px, rows 44px (dense: 36px), cells padded 12px horizontally
  - row hover `--surface-2`, and the selected row gets a 2px primary left border
  - checkbox column 40px, actions column right-aligned with icon buttons
- **Cards:** `--surface` with a 1px `--border` and radius-card, padding 16px (dashboard 20px). **No shadows**, except menus, popovers and dialogs (`0 8px 24px rgb(0 0 0 / 0.12)`).
- **Icons:** lucide-react, 16px in controls and text, 20px in empty states and nav, stroke 1.75. Vertically centre them with flex. Never use baseline-aligned icons.

## States are part of the design

Every data view ships all of these, at the same dimensions as the loaded state (no layout jump):
- **Loading:** a skeleton in the exact shape of the content (rows, thumbnails). A spinner only inside buttons that are busy (which keep their width).
- **Empty:** a 20px icon, a 14px line saying what this is, and **one primary action** (see the `guided-experience` skill).
- **Error:** what happened, plus what to do, plus a Retry button. Never a raw stack trace or error code alone.
- **Processing** (OCR, AI): a status badge with an animated dot, the stage name ("Reading text…", "Classifying…") and the elapsed time.

## Accessibility & motion (non-negotiable)

- Every control has a visible label or an `aria-label`. Focus is visible (the ring token) and the tab order is logical.
- Contrast is AA (the tokens above pass; check any new colour). Information is never shown by colour alone.
- Motion is 150 ms ease-out for hover and focus, 200 ms for dialogs and popovers. Honour `prefers-reduced-motion` (no transforms).
- Touch targets are at least 40px on mobile (use `--control-h-lg` for primary mobile actions).

## Done when

- [ ] Tokens only (no hard-coded colours, sizes or heights). The page title is ≤ 20px.
- [ ] Every control uses `control`/`controlSm` and appears on `/dev/ui`. The height test passes.
- [ ] Header, forms, toolbars and tables follow the alignment rules at 375, 768 and 1280 px, in light and dark.
- [ ] Loading, empty, error and processing states exist and match the loaded layout.
- [ ] axe reports no violations, and keyboard-only use works.
