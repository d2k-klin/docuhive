UV ?= uv
NPM ?= npm
DIR ?=
OUT ?= tmp/ocr-spike
EX ?=

.PHONY: setup dev test test-ui test-integration lint fmt db-upgrade openapi gen-api spike-ocr ocr-smoke up down logs backup learn license-check

setup:
	$(UV) sync --all-packages --all-extras --dev
	$(NPM) ci
	$(UV) run pre-commit install

dev:
	docker compose -f deploy/compose.dev.yml up -d --wait
	$(UV) run docuhive db upgrade
	$(UV) run python deploy/scripts/dev.py

test:
	$(UV) run pytest -m "not integration" --cov=docuhive --cov-report=term-missing --cov-fail-under=85
	$(NPM) test

test-ui:
	$(NPM) run build
	$(NPM) exec --workspace apps/web -- playwright test

test-integration:
	docker compose -f deploy/compose.test.yml up -d --wait
	DOCUHIVE_TEST_DATABASE_URL=postgresql+psycopg://docuhive_test:docuhive_test@127.0.0.1:55432/docuhive_test $(UV) run pytest -m 'integration and not system'

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run mypy
	$(UV) run pytest -q tests/unit/test_docs.py
	$(NPM) run lint
	$(NPM) run typecheck

fmt:
	$(UV) run ruff check --fix .
	$(UV) run ruff format .
	$(NPM) run format

db-upgrade:
	$(UV) run docuhive db upgrade

openapi:
	$(UV) run docuhive openapi

gen-api:
	$(UV) run docuhive openapi > apps/web/lib/api/openapi.json
	$(NPM) run gen:api --workspace apps/web

spike-ocr:
	test -n "$(DIR)" || (echo 'Set DIR to the private sample folder'; exit 1)
	$(UV) run docuhive spike ingest "$(DIR)" --out "$(OUT)"

# Real OCR inside the worker image (unit tests mock ocrmypdf).
ocr-smoke:
	docker build -f services/docuhive/Dockerfile -t docuhive-worker:ocr-smoke .
	docker run --rm -i --entrypoint python docuhive-worker:ocr-smoke - < deploy/scripts/ocr_smoke.py

PROD_ENV ?= .env.production
PROD_COMPOSE = docker compose --env-file $(PROD_ENV) -f deploy/compose.yml

up:
	$(PROD_COMPOSE) up -d --wait

down:
	$(PROD_COMPOSE) down

logs:
	$(PROD_COMPOSE) logs --follow --tail 100

backup:
	DOCUHIVE_PROD_ENV=$(abspath $(PROD_ENV)) deploy/scripts/backup.sh

.PHONY: images upgrade test-capture test-ops verify-restore
images:
	$(PROD_COMPOSE) build api web

upgrade:
	test -n "$(NEXT_ENV)"
	DOCUHIVE_PROD_ENV=$(abspath $(PROD_ENV)) deploy/scripts/upgrade.sh "$(NEXT_ENV)"

test-capture:
	$(UV) run pytest services/docuhive/tests/core/test_capture_operations.py -q
	$(NPM) test --workspace apps/web
	$(NPM) exec --workspace apps/web -- playwright test tests/ui/capture.spec.ts

test-ops:
	$(UV) run pytest services/docuhive/tests/core/test_backup_script.py services/docuhive/tests/core/test_operations_integration.py -q

verify-restore:
	$(UV) run python deploy/drills/verify_snapshot.py "$(ORIGINAL)" "$(RESTORED)"

learn:
	$(UV) run python examples/learn/run.py "$(EX)"

license-check:
	$(UV) run python deploy/scripts/check_licenses.py
	$(NPM) exec -- license-checker --production --failOn 'AGPL;AGPL-3.0;AGPL-3.0-only;AGPL-3.0-or-later' --excludePrivatePackages

# QA owns these additive targets. Contract tests use a separate disposable DB.
QA_RUN = UV_CACHE_DIR=$(CURDIR)/tmp/qa/uv-cache UV_PROJECT_ENVIRONMENT=.venv-qa $(UV) run --frozen --all-packages --all-extras
QA_COMPOSE = docker compose -f deploy/compose.e2e.yml
QA_TRACE_ARGS ?=

.PHONY: qa-check qa-up qa-down qa-system qa-contracts qa-corpus qa-trace qa-boundaries qa-e2e qa-e2e-smoke qa-perf qa-drills qa-nightly qa-release

qa-check:
	$(QA_RUN) pytest tests/system services/docuhive/tests/contracts -m 'not integration' -q

qa-up:
	$(QA_RUN) python tests/system/tools/cert.py
	$(QA_COMPOSE) up -d --build --wait

qa-down:
	$(QA_COMPOSE) down --volumes --remove-orphans

qa-system:
	$(QA_RUN) pytest tests/system -m 'integration and not slow' -q

.PHONY: qa-provider-smoke
qa-provider-smoke:
	$(QA_COMPOSE) exec -T api python tests/mocks/smoke.py

qa-contracts:
	DOCUHIVE_TEST_DATABASE_URL=postgresql+psycopg://docuhive_test:docuhive_test@127.0.0.1:55433/docuhive_contract_test $(QA_RUN) pytest services/docuhive/tests/contracts -q

qa-corpus:
	$(QA_RUN) python tests/corpus/generate.py

qa-trace:
	$(QA_RUN) python tests/system/tools/trace.py $(QA_TRACE_ARGS)

qa-boundaries:
	$(QA_RUN) lint-imports --no-cache

qa-e2e:
	$(QA_RUN) python tests/system/tools/browser.py

qa-e2e-smoke:
	$(QA_RUN) python tests/system/tools/browser.py --grep @smoke

qa-perf:
	$(QA_RUN) python tests/perf/search_bench.py

qa-drills:
	$(QA_RUN) python tests/system/tools/release.py --drills

qa-nightly:
	$(MAKE) -k qa-check qa-corpus qa-system qa-contracts qa-e2e qa-provider-smoke qa-bundle qa-audit qa-perf qa-drills

qa-release:
	$(QA_RUN) python tests/system/tools/trace.py --strict
	$(QA_RUN) python tests/system/tools/release.py

.PHONY: qa-audit qa-bundle
qa-audit:
	$(QA_RUN) pytest -m 'not integration' --cov=docuhive --cov-report=json:tmp/qa/coverage.json --cov-report=term --cov-fail-under=85
	$(QA_RUN) python tests/system/tools/audit.py

qa-bundle:
	mkdir -p tmp/qa/web-static
	$(QA_COMPOSE) cp web:/app/apps/web/.next/static/. tmp/qa/web-static
	$(QA_RUN) python tests/system/tools/bundle.py
