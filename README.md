# docuhive

Self-hosted, AI-first document hub: email and mobile capture, OCR, automatic categorisation, hybrid search and Q&A across your documents with local or cloud AI. Documents live in a self-describing vault on your own storage.

- [Requirements](docs/REQUIREMENTS.md)
- [Implementation plan](docs/IMPLEMENTATION_PLAN.md)

## Development

The implementation is in progress. See [Developer OA status](docs/Developer-OA/STATUS.md)
and [the execution plan](docs/Developer-OA/EXECUTION_PLAN.md) for implemented work
and pending acceptance gates.

```sh
make setup
docker compose -f deploy/compose.dev.yml up -d --wait
make db-upgrade
uv run docuhive user create admin --admin
make dev
```

The full instructions are in [Development setup](docs/setup/development.md).

| Guide | Purpose |
| --- | --- |
| [All documentation](docs/README.md) | Using, understanding, learning and extending |
| [Contributing](CONTRIBUTING.md) | Commands, checks and contribution rules |
| [Security](SECURITY.md) | Private vulnerability reporting |
| [License](LICENSE) | Apache-2.0 |
- [Work split for two developers](docs/shared/README.md): [Developer OA](docs/Developer-OA/README.md), [Developer CL](docs/Developer-CL/README.md)
- [Project skills](.agents/skills/README.md) (conventions for humans and coding agents)
