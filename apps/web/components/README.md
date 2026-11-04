# `apps/web/components`

**Overview.** React components, split by owner: `ui` for the design-system primitives, `core` for platform screens and `intel` for AI and email features.

## What's here

| Path | What it is |
| --- | --- |
| [`core/`](core/) | Components for the platform screens: sign-in and the user menu |
| [`intel/`](intel/) | Components for the AI and email features, including the slots the platform screens render: dashboard widgets, the document AI panel, similar documents, the search hint and the setup-wizard steps |
| [`ui/`](ui/) | Design-system primitives (shadcn/ui, restyled to the DocuHive tokens) |

## Extending

Build on `ui` primitives and style them with the tokens from `app/globals.css`; never hard-code colours or sizes.
