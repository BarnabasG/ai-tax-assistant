# HMRC RAG Assistant - Setup & Porting Guide

This project is a high-performance RAG (Retrieval-Augmented Generation) system for HMRC tax manuals. This guide explains how to set it up on a new machine.

## Prerequisites

Ensure you have the following installed:
- **Node.js** (v18+) & **npm**
- **Python** (3.12+)
- **Docker** (for the vector database)
- **Ollama** (for local models)
- **uv** (Recommended Python package manager: `pip install uv`)

## Quick Start

### 1. Clone & Infrastructure
```bash
git clone https://github.com/BarnabasG/ai-tax-assistant.git
cd ai-tax-assistant
docker-compose up -d  # Starts Qdrant Vector Database
```

### 2. Backend Configuration
Navigate to the `backend` folder and create a `.env` file:
```bash
cd backend
touch .env
```
Add the following configuration (see `.env.example` for reference):
```env
OLLAMA_URL=http://localhost:11434
GEMINI_API_KEY=your_key_here  # Optional: for cloud models
DEFAULT_CHAT_MODEL=qwen3.5:9b
QDRANT_URL=http://localhost:6333
```

### 3. Data Ingestion
The system needs to fetch and index HMRC manuals.
```bash
# From the backend directory
uv sync                          # Install dependencies
uv run python -m etl.discover    # Find manuals
uv run python -m etl.fetch       # Download content
uv run python -m etl.ingest      # Embed and index into Qdrant
```

### 4. Running the App
Use the provided Makefile from the root directory:
```bash
# In one terminal (Backend)
make api

# In another terminal (Frontend)
make frontend
```

## Customizing Models
- **Local Models**: Install any model via Ollama (e.g., `ollama run qwen3.5:9b`). Update `backend/api.py` in the `list_models` function to display them in the UI.
- **Cloud Models**: Add your `GEMINI_API_KEY` to `.env`. The system is pre-configured to route specific model IDs to the Gemini API in `backend/llm.py`.

## Project Structure
- `/frontend`: Next.js application with a modernized chat interface.
- `/backend`: FastAPI service handling RAG logic, streaming, and embeddings.
- `/backend/etl`: Scripts for discovery, fetching, and indexing HMRC data.
- `/backend/data`: Local storage for raw JSON and processed text.
