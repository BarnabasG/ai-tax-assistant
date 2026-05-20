import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock

from src.api import app

@pytest.fixture
def client():
    return TestClient(app)

class MockPayload:
    def __init__(self, data):
        self.payload = data
        self.score = 0.9

@pytest.fixture(autouse=True)
def mock_deps():
    with patch("src.api.store") as mock_store, \
         patch("src.api.embed_query", new_callable=AsyncMock) as mock_embed, \
         patch("src.api.generate_sparse_vector") as mock_sparse, \
         patch("src.api.stream_rag_answer") as mock_stream, \
         patch("src.etl.parse.parse_section") as mock_parse, \
         patch("src.api.router.stream_chat") as mock_stream_chat, \
         patch("src.api.router.get_available_models", new_callable=AsyncMock) as mock_models:
         
        # default mocks
        mock_embed.return_value = [0.1, 0.2]
        mock_sparse.return_value = {"indices": [1], "values": [0.5]}
        
        mock_store.hybrid_search = AsyncMock(return_value=[
            MockPayload({"manual_slug": "VIT", "manual_title": "VAT", "section_id": "VIT123", "title": "Test Title"})
        ])

        mock_store.get_by_section_id = AsyncMock(return_value=[
            MockPayload({
                "manual_slug": "VIT", "manual_title": "VAT", "section_id": "VIT123", "title": "Test Title",
                "related_pages": [], "breadcrumb": [], "gov_url": "http://gov.uk", "updated_at": "2024-01-01",
                "text": "Chunk text"
            })
        ])
        mock_parse.return_value = {"text": "Full text from parse_section"}
        
        mock_store.search_by_title = AsyncMock(return_value=[
            MockPayload({"section_id": "VIT123", "title": "Test Title", "manual_title": "VAT"})
        ])

        mock_store.get_sections_for_manual = AsyncMock(return_value=[
            MockPayload({"section_id": "VIT123", "title": "Test Title", "breadcrumb": []})
        ])
        
        mock_models.return_value = {"models": [{"id": "gemma3", "name": "Gemma 3", "provider": "cloud"}], "ollama_running": True}

        async def stream_chat_gen(*args, **kwargs):
            yield '{"token": "Test "}'
            yield '{"token": "Title"}'
        mock_stream_chat.side_effect = stream_chat_gen

        async def mock_stream_rag(*args, **kwargs):
            yield b'{"token": "Hello"}'
        mock_stream.side_effect = mock_stream_rag

        yield {
            "store": mock_store,
            "embed": mock_embed,
            "sparse": mock_sparse,
            "parse": mock_parse,
            "stream_chat": mock_stream_chat,
            "models": mock_models
        }

def test_chat(coverage_client):
    response = coverage_client.post("/chat", json={"query": "hello"})
    assert response.status_code == 200

def test_search(coverage_client):
    response = coverage_client.post("/search", json={"query": "hello", "limit": 10})
    assert response.status_code == 200
    assert "groups" in response.json()

def test_generate_title(coverage_client):
    response = coverage_client.post("/generate-title", json={"query": "hello", "model": "test-model"})
    assert response.status_code == 200
    assert response.json() == {"title": "Test Title"}

def test_generate_title_fallback(coverage_client, mock_deps):
    # Simulate an error on the primary model, to trigger fallback logic
    async def failing_stream_chat(messages, model_name):
        if model_name == "gemma3:12b-cloud":
            raise Exception("Model offline")
            yield ""
        yield '{"token": "Fallback "}'
        yield '{"token": "Title"}'
        
    mock_deps["stream_chat"].side_effect = failing_stream_chat
    
    response = coverage_client.post("/generate-title", json={"query": "hello", "model": "fallback-model"})
    assert response.status_code == 200
    assert response.json() == {"title": "Fallback Title"}

def test_generate_title_failure(coverage_client, mock_deps):
    # Simulate an error on all models
    async def failing_stream_chat(messages, model_name):
        raise Exception("Model offline")
        yield ""
        
    mock_deps["stream_chat"].side_effect = failing_stream_chat
    
    response = coverage_client.post("/generate-title", json={"query": "hello world test query for fallback", "model": "fallback-model"})
    assert response.status_code == 200
    assert response.json()["title"].startswith("hello world test query")

def test_page(coverage_client):
    response = coverage_client.get("/page?code=VIT123")
    assert response.status_code == 200
    assert response.json()["text"] == "Full text from parse_section"

def test_page_not_found(coverage_client, mock_deps):
    mock_deps["store"].get_by_section_id = AsyncMock(return_value=[])
    response = coverage_client.get("/page?code=MISSING")
    assert response.status_code == 200
    assert response.json() == {"error": "Page not found"}

def test_page_no_cache(coverage_client, mock_deps):
    mock_deps["parse"].return_value = None
    response = coverage_client.get("/page?code=VIT123")
    assert response.status_code == 200
    assert "[Warning: Document too long and local cache missing, showing partial chunk]" in response.json()["text"]

def test_autocomplete(coverage_client):
    response = coverage_client.get("/autocomplete?q=hel")
    assert response.status_code == 200
    assert len(response.json()["suggestions"]) == 1
    
def test_autocomplete_short(coverage_client):
    response = coverage_client.get("/autocomplete?q=he")
    assert response.status_code == 200
    assert len(response.json()["suggestions"]) == 0

def test_manual_tree(coverage_client):
    response = coverage_client.get("/manual-tree?manual=VIT")
    assert response.status_code == 200
    assert len(response.json()["sections"]) == 1
