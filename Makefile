SHELL := bash
PROMPT ?= prompts/system_v1.txt

.PHONY: setup run test lint eval gate load up

setup:
	python3 -m venv .venv && .venv/bin/pip install -e '.[dev,load]'

run:  ## local dev server (loads .env)
	set -a; [ -f .env ] && . ./.env; set +a; .venv/bin/uvicorn serving.app:create_app --factory --reload

up:   ## full stack: app + redis + prometheus + grafana
	docker compose up --build

test:
	.venv/bin/ruff check . && .venv/bin/pytest -q

lint:
	.venv/bin/ruff check .

gate eval:  ## regression gate against the real upstream: make gate PROMPT=prompts/system_degraded.txt
	set -a; [ -f .env ] && . ./.env; set +a; .venv/bin/python -m eval.gate --prompt $(PROMPT)

load:  ## needs the stack running on :8000
	.venv/bin/locust -f eval/locustfile.py --host http://localhost:8000 -u 50 -r 10 -t 2m --headless
