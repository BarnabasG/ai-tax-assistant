# HMRC RAG Assistant

A high-performance Retrieval-Augmented Generation (RAG) system for querying HMRC (UK Tax) internal manuals using local AI models.

## Features
- **Local AI**: Fully private and offline inference using Ollama.
- **Cloud Models**: Integrate with Ollama's hosted Cloud Models for heavier workloads.
- **Hybrid Search**: Combines Dense Vector Search and BM25 Sparse Search for highly accurate retrieval.
- **Live HMRC Data**: Scrapes and indexes official HMRC tax manuals directly from GOV.UK.
- **Auto-Discovery**: Automatically detects models installed in your local Ollama instance.

---

## Quick Start Setup

### 1. Prerequisites
Ensure you have the following installed on your machine:
- **[Docker Desktop](https://www.docker.com/products/docker-desktop/)**: Required to run the Qdrant vector database.
- **[Ollama](https://ollama.com/)**: Required for running the AI models locally.
- **Node.js (v18+) & npm**: For the frontend.
- **Python (3.12+)**: For the backend.
- **uv**: (Highly Recommended) Fast Python package manager. `pip install uv`

### 2. Start the Database
The vector database runs in a Docker container. Ensure Docker Desktop is open, then run:
```bash
docker-compose up -d
```

### 3. Install AI Models
Pull your preferred model using Ollama. The app will automatically detect it:
```bash
ollama pull qwen3.5:9b
```

### 4. Setup the Backend
```bash
cd backend
cp .env.example .env
```
*(Optional: Edit `.env` to configure a remote Ollama server if you have one).*

### 5. Using Cloud Models (Optional)
1. Sign up for a free account at [ollama.com](https://ollama.com/)
2. Open your terminal and log in using the Ollama CLI:
   ```bash
   ollama login
   ```
Once authenticated, the UI will automatically route cloud model requests through your local Ollama instance to the cloud provider securely.

### 5. Ingest Data (Pick one method)
You need to populate the database with the HMRC manuals.

**Method A: Restore from Snapshot (Fastest)**
If a pre-computed `hmrc_data.snapshot` file is provided, place it in the `backend/data/` folder and run:
```bash
make import-data
```
*Note: A point-in-time snapshot of HMRC Legislation from May 2026 is available on [release v1.0.0](https://github.com/BarnabasG/ai-tax-assistant/releases/tag/v1.0.0)*

**Method B: Build from Scratch**
Run the automated ETL pipeline to download and index everything from GOV.UK. 
*Note: This requires Ollama to be running and an embedding model (default: `nomic-embed-text`) to be pulled beforehand.*
```bash
make ingest
```

### 6. Run the Application
Open two terminal windows in the project root:

**Terminal 1 (Backend API):**
```bash
make api
```

**Terminal 2 (Frontend UI):**
```bash
make frontend
```

Navigate to `http://localhost:3000` in your browser.

---

## Command Reference

A `Makefile` is included to simplify common tasks. Run these from the project root:

| Command | Description |
|---|---|
| `make frontend` | Starts the Next.js development server |
| `make api` | Starts the FastAPI backend server |
| `make ingest` | Runs the full ETL pipeline (Discover, Fetch, Parse, Embed) |
| `make export-data` | Exports the database to `backend/data/hmrc_data.snapshot` for easy sharing |
| `make import-data` | Restores the database from a `.snapshot` file |
| `make update` | Checks for new HMRC manual updates and re-indexes only changes |
| `make clean` | **WARNING:** Wipes the entire vector database |
