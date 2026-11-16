# School letters (`schule`)

**Overview.** The smallest useful plugin, and the one the [plugins guide](../README.md#build-your-own-plugin) builds step by step. DocuHive learns a new kind of document, the school letter, reads the date by which it needs an answer, reminds you a week and a day before, and lists the open ones on one screen. Every letter is also tagged `school`.

## Set it up

1. `docuhive plugins add plugins-example/schule`, restart DocuHive.
2. Switch it on under **Settings → Plugins**.
3. Upload a letter from school. It appears under **School** with its reply date.

## Make it yours

| File | What it controls |
| --- | --- |
| `pages/letters.yaml` | The list: its columns and which letters it shows |

## What's here

| Path | What it is |
| --- | --- |
| `plugin.yaml` | The new document type and its reply date |
| `plugin.py` | Tags each school letter `school` |
| `pages/letters.yaml` | The list of letters still waiting for an answer |
| `tests/` | Its tests |
