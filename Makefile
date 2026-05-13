.PHONY: ingest api frontend update evaluate clean

ingest:
	cd backend && uv run python -m etl.ingest

api:
	cd backend && uv run uvicorn api:app --host 0.0.0.0 --port 8000 --reload

frontend:
	cd frontend && npm run dev

update:
	cd backend && uv run python -m etl.update

evaluate:
	cd backend && uv run python evaluate.py

clean:
	cd backend && uv run python -c "from qdrant_store import store; import asyncio; asyncio.run(store.wipe())"

export-data:
	cd backend && uv run python snapshot.py export

import-data:
	cd backend && uv run python snapshot.py import
