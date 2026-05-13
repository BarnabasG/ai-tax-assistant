import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from rag import verify_citations, embed_query, stream_rag_answer

@pytest.mark.parametrize("response, allowed, expected", [
    ("According to [VIT12345], yes.", {"VIT12345"}, []),
    ("Check [VIT12345] and [HALLU9999].", {"VIT12345"}, ["HALLU9999"]),
    ("No citations here.", {"VIT12345"}, []),
    ("Invalid [VIT12] code.", {"VIT12345"}, []),
])
def test_verify_citations(response, allowed, expected):
    assert verify_citations(response, allowed) == expected

@pytest.mark.asyncio
async def test_embed_query_success():
    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={"embeddings": [[0.1, 0.2, 0.3]]})
        mock_post.return_value.__aenter__.return_value = mock_resp
        
        result = await embed_query("test query")
        assert result == [0.1, 0.2, 0.3]

@pytest.mark.asyncio
async def test_embed_query_failure():
    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status = 500
        mock_post.return_value.__aenter__.return_value = mock_resp
        
        result = await embed_query("test query")
        assert result == []

@pytest.mark.asyncio
async def test_stream_rag_answer():
    with patch("rag.embed_query", new_callable=AsyncMock) as mock_embed, \
         patch("rag.generate_sparse_vector") as mock_sparse, \
         patch("rag.store.hybrid_search") as mock_search, \
         patch("rag.router.stream_chat") as mock_stream:
        
        mock_embed.return_value = [0.1]
        mock_sparse.return_value = {"indices": [1], "values": [0.5]}
        
        mock_result = MagicMock()
        mock_result.payload = {
            "section_id": "VIT123",
            "manual_title": "VAT",
            "title": "Test Section",
            "text": "Context text"
        }
        mock_search.return_value = [mock_result]
        
        async def mock_gen(*args, **kwargs):
            yield json.dumps({"token": "Hello"})
            yield json.dumps({"token": " [VIT123]"})
            
        mock_stream.side_effect = mock_gen
        
        chunks = []
        async for chunk in stream_rag_answer("query", [], "model"):
            chunks.append(chunk)
            
        assert len(chunks) > 0
        # Final chunk should be metadata
        final_chunk = json.loads(chunks[-1])
        assert final_chunk["done"] is True
        assert final_chunk["sources"][0]["section_id"] == "VIT123"
        assert final_chunk["hallucinated_citations"] == []

@pytest.mark.asyncio
async def test_stream_rag_answer_no_results():
    with patch("rag.embed_query", new_callable=AsyncMock) as mock_embed, \
         patch("rag.generate_sparse_vector") as mock_sparse, \
         patch("rag.store.hybrid_search") as mock_search:
        
        mock_embed.return_value = [0.1]
        mock_sparse.return_value = {}
        mock_search.return_value = []
        
        chunks = []
        async for chunk in stream_rag_answer("query", [], "model"):
            chunks.append(chunk)
            
        data = json.loads(chunks[0])
        assert "could not find any relevant HMRC guidance" in data["token"]

@pytest.mark.asyncio
async def test_stream_rag_answer_embed_fail():
    with patch("rag.embed_query", new_callable=AsyncMock) as mock_embed:
        mock_embed.return_value = []
        
        chunks = []
        async for chunk in stream_rag_answer("query", [], "model"):
            chunks.append(chunk)
            
        data = json.loads(chunks[0])
        assert "error" in data
        assert "Failed to embed" in data["error"]
