.PHONY: ingest ingest-mainstream api frontend update update-mainstream update-manuals evaluate clean export-data import-data test cover test-ui cover-ui

ingest:
	cd backend && uv run python -m src.etl.ingest

ingest-mainstream:
	cd backend && uv run python -m src.etl.ingest --mainstream

api:
	cd backend && uv run python -m src.api

frontend:
	cd frontend && npm run dev

update:
	cd backend && uv run python -m src.etl.update

update-mainstream:
	cd backend && uv run python -m src.etl.update --mainstream

update-manuals:
	cd backend && uv run python -m src.etl.update --manuals

evaluate:
	cd backend && uv run python -m src.evaluate

assess-content:
	cd backend && uv run python scratch/assess_manuals.py

clean:
	cd backend && uv run python -c "from src.qdrant_store import store; import asyncio; asyncio.run(store.wipe())"

export-data:
	cd backend && uv run python -m src.snapshot export

import-data:
	cd backend && uv run python -m src.snapshot import

test:
	cd backend && uv run pytest

cover:
	cd backend && uv run pytest --cov src --cov-report=term-missing --api-cov-report

test-ui:
	cd frontend && npm run test

cover-ui:
	cd frontend && npm run test -- --coverage
