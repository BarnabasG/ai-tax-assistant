import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.qdrant_store import QdrantStore, COLLECTION
from qdrant_client import models

@pytest.fixture
def store():
    return QdrantStore()

def test_store_connect(store):
    with patch("src.qdrant_store.AsyncQdrantClient") as mock_client:
        store.connect()
        assert store.client is not None
        mock_client.assert_called_once()

@pytest.mark.asyncio
async def test_ensure_collection(store):
    mock_client = MagicMock()
    store.client = mock_client
    
    mock_client.get_collections = AsyncMock()
    mock_client.create_collection = AsyncMock()
    mock_client.get_collection = AsyncMock()
    mock_client.create_payload_index = AsyncMock()
    
    # Collection exists
    mock_coll = MagicMock()
    mock_coll.name = COLLECTION
    mock_client.get_collections.return_value = MagicMock(collections=[mock_coll])
    mock_client.get_collection.return_value = MagicMock(payload_schema={})
    
    await store.ensure_collection()
    mock_client.create_collection.assert_not_called()
    
    # Collection does not exist
    mock_client.get_collections.return_value = MagicMock(collections=[])
    await store.ensure_collection()
    mock_client.create_collection.assert_called_once()

@pytest.mark.asyncio
async def test_hybrid_search(store):
    mock_client = MagicMock()
    store.client = mock_client
    
    mock_client.query_points = AsyncMock(return_value=MagicMock(points=[MagicMock()]))
    
    dense = [0.1] * 768
    sparse = models.SparseVector(indices=[1], values=[0.5])
    
    results = await store.hybrid_search(dense, sparse, limit=5, manual_filter="VIT")
    
    assert len(results) == 1
    mock_client.query_points.assert_called_once()
    # Check if filter was applied
    args, kwargs = mock_client.query_points.call_args
    assert kwargs["limit"] == 5
    assert kwargs["prefetch"][0].filter is not None

@pytest.mark.asyncio
async def test_search_by_title(store):
    mock_client = MagicMock()
    store.client = mock_client
    mock_client.scroll = AsyncMock(return_value=([MagicMock()], None))
    
    results = await store.search_by_title("VAT")
    assert len(results) == 1
    mock_client.scroll.assert_called_once()

@pytest.mark.asyncio
async def test_get_by_section_id(store):
    mock_client = MagicMock()
    store.client = mock_client
    mock_client.scroll = AsyncMock(return_value=([MagicMock()], None))
    
    results = await store.get_by_section_id("VIT123")
    assert len(results) == 1

@pytest.mark.asyncio
async def test_get_sections_for_manual(store):
    mock_client = MagicMock()
    store.client = mock_client
    mock_client.scroll = AsyncMock(return_value=([MagicMock()], None))
    
    results = await store.get_sections_for_manual("VAT")
    assert len(results) == 1

@pytest.mark.asyncio
async def test_count(store):
    mock_client = MagicMock()
    store.client = mock_client
    mock_client.get_collection = AsyncMock(return_value=MagicMock(points_count=100))
    
    assert await store.count() == 100

@pytest.mark.asyncio
async def test_wipe(store):
    mock_client = MagicMock()
    store.client = mock_client
    mock_client.delete_collection = AsyncMock()
    
    with patch.object(store, "ensure_collection", new_callable=AsyncMock) as mock_ensure:
        await store.wipe()
        mock_client.delete_collection.assert_called_once_with(COLLECTION)
        mock_ensure.assert_called_once()
