import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from embed import chunk_text, generate_embeddings

@pytest.mark.parametrize("text, size, overlap, expected_count", [
    ("This is a test. This is only a test.", 20, 5, 3),
    ("Short.", 100, 10, 1),
    ("", 100, 10, 0),
    ("Sentence one. Sentence two. Sentence three.", 15, 5, 4),
])
def test_chunk_text(text, size, overlap, expected_count):
    chunks = chunk_text(text, chunk_size=size, overlap=overlap)
    assert len(chunks) == expected_count

@pytest.mark.asyncio
async def test_generate_embeddings_success():
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={"embeddings": [[0.1, 0.2], [0.3, 0.4]]})
    mock_session.post.return_value.__aenter__.return_value = mock_resp
    
    result = await generate_embeddings(mock_session, ["text1", "text2"])
    assert result == [[0.1, 0.2], [0.3, 0.4]]

@pytest.mark.asyncio
async def test_generate_embeddings_unreachable():
    mock_session = MagicMock()
    import aiohttp
    mock_session.post.side_effect = aiohttp.ClientConnectorError(MagicMock(), MagicMock())
    
    with pytest.raises(aiohttp.ClientConnectorError):
        await generate_embeddings(mock_session, ["text"])

@pytest.mark.asyncio
async def test_generate_embeddings_fallback():
    mock_session = MagicMock()
    
    # First call (batch) fails with 400
    mock_resp_fail = MagicMock()
    mock_resp_fail.status = 400
    mock_resp_fail.text = AsyncMock(return_value="Bad input")
    
    # Second/Third calls (sequential retry) succeed
    mock_resp_success = MagicMock()
    mock_resp_success.status = 200
    mock_resp_success.json = AsyncMock(return_value={"embeddings": [[0.5]]})
    
    mock_session.post.return_value.__aenter__.side_effect = [
        mock_resp_fail,
        mock_resp_success,
        mock_resp_success
    ]
    
    result = await generate_embeddings(mock_session, ["text1", "text2"])
    assert result == [[0.5], [0.5]]

@pytest.mark.asyncio
async def test_embed_and_upsert_batch():
    mock_session = MagicMock()
    docs = [{
        "section_id": "VIT123",
        "manual_slug": "vat",
        "manual_title": "VAT",
        "title": "Title",
        "text": "Short text content",
        "tax_type": "VAT",
        "related_pages": [],
        "breadcrumb": [],
        "gov_url": "url",
        "updated_at": "date"
    }]
    
    with patch("embed.generate_embeddings", new_callable=AsyncMock) as mock_embed, \
         patch("embed.generate_sparse_vector_passage") as mock_sparse, \
         patch("embed.store.upsert_batch") as mock_upsert:
        
        mock_embed.return_value = [[0.1] * 768]
        mock_sparse.return_value = MagicMock(indices=[1], values=[0.5])
        
        from embed import embed_and_upsert_batch
        await embed_and_upsert_batch(mock_session, docs)
        
        mock_upsert.assert_called_once()
        args, _ = mock_upsert.call_args
        assert len(args[0]) == 1

@pytest.mark.asyncio
async def test_process_pipeline():
    docs = [{"id": i} for i in range(10)]
    with patch("embed.store.ensure_collection", new_callable=AsyncMock), \
         patch("embed.embed_and_upsert_batch", new_callable=AsyncMock) as mock_upsert:
        
        from embed import process_pipeline
        batches = []
        async for batch in process_pipeline(docs):
            batches.append(batch)
            
        assert len(batches) > 0
        mock_upsert.assert_called()

def test_handle_shutdown():
    from embed import handle_shutdown
    with patch("os._exit") as mock_exit:
        # First call sets SHUTTING_DOWN
        handle_shutdown(None, None)
        # Second call exits
        handle_shutdown(None, None)
        mock_exit.assert_called_once_with(1)
