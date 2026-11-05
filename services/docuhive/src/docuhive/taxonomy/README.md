# `services/docuhive/src/docuhive/taxonomy`

**Overview.** The controlled vocabulary (categories, document types, tags and facts) the AI chooses from.

## What's here

| Path | What it is |
| --- | --- |
| [`__init__.py`](__init__.py) | Taxonomy loader: config/defaults/taxonomy.yaml + overlay, validated and cached |
| [`routes.py`](routes.py) | Taxonomy, enabled category selection and custom categories |

## Extending

Your own taxonomy goes into the private overlay; it replaces the default lists.

Administrators choose shared categories in Vocabulary. Preferences are saved in the existing settings table and are read fresh by each process. Disabled categories remain in the taxonomy for existing documents and privacy routing. File and overlay values remain the initial presets.
