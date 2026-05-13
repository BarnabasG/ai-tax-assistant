.PHONY: ingest api frontend update evaluate clean export-data import-data test cover test-ui cover-ui

ingest:
	cd backend && uv run python -m src.etl.ingest

api:
	cd backend && uv run uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload

frontend:
	cd frontend && npm run dev

update:
	cd backend && uv run python -m src.etl.update

evaluate:
	cd backend && uv run python src/evaluate.py

clean:
	cd backend && uv run python -c "from src.qdrant_store import store; import asyncio; asyncio.run(store.wipe())"

export-data:
	cd backend && uv run python src/snapshot.py export

import-data:
	cd backend && uv run python src/snapshot.py import

test:
	cd backend && uv run pytest

cover:
	cd backend && uv run pytest --cov src --cov-report=term-missing --api-cov-report

test-ui:
	cd frontend && npm run test

cover-ui:
	cd frontend && npm run test -- --coverage
