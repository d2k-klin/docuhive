# `config/defaults`

**Overview.** Public configuration defaults are merged with the private overlay.

## What's here

CL supplies taxonomy, model routing, mail rules and prompts. Until those exist,
`load_yaml` returns an empty mapping for missing files.

## Extending

Keep public defaults synthetic. Overlay mappings merge recursively; lists replace.
