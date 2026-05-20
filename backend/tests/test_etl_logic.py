import pytest
import json
import os
from unittest.mock import AsyncMock, patch, MagicMock, mock_open
from src.etl.discover import discover_all_manuals, get_manual_sections, discover_all
from src.etl.fetch import fetch_section, fetch_all
from src.etl.update import run_update
from src.etl.ingest import run_pipeline

@pytest.mark.asyncio
async def test_get_manual_sections_recursive():
    mock_session = MagicMock()
    
    # First call: root manual, has children
    mock_resp_root = MagicMock()
    mock_resp_root.status = 200
    mock_resp_root.json = AsyncMock(return_value={
        "details": {
            "child_section_groups": [{"child_sections": [{"base_path": "/child"}]}]
        }
    })
    
    # Second call: child section, is leaf
    mock_resp_child = MagicMock()
    mock_resp_child.status = 200
    mock_resp_child.json = AsyncMock(return_value={
        "details": {"body": "Leaf content", "section_id": "VIT123"},
        "title": "Child"
    })
    
    mock_session.get.return_value.__aenter__.side_effect = [mock_resp_root, mock_resp_child]
    
    semaphore = AsyncMock()
    sections = await get_manual_sections(mock_session, "VAT", "VAT Manual", semaphore)
    assert len(sections) == 1
    assert sections[0]["section_id"] == "VIT123"

@pytest.mark.asyncio
async def test_fetch_section_404():
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status = 404
    mock_session.get.return_value.__aenter__.return_value = mock_resp
    
    section = {"manual_slug": "VAT", "section_id": "VIT123", "base_path": "/vat/vit123"}
    semaphore = AsyncMock()
    
    with patch("os.makedirs"), patch("os.path.exists", return_value=False):
        success = await fetch_section(mock_session, section, semaphore)
        assert success is False

@pytest.mark.asyncio
async def test_fetch_section_exception():
    mock_session = MagicMock()
    
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={})
    
    # Create two context manager mocks: one that raises, one that succeeds
    m1 = MagicMock()
    m1.__aenter__.side_effect = Exception("error")
    
    m2 = MagicMock()
    m2.__aenter__.return_value = mock_resp

    mock_session.get.side_effect = [m1, m2]

    section = {"manual_slug": "VAT", "section_id": "VIT123", "base_path": "/vat/vit123"}
    semaphore = AsyncMock()
    with patch("os.makedirs"), patch("os.path.exists", return_value=False), patch("builtins.open", mock_open()), patch("asyncio.sleep", new_callable=AsyncMock):
        from etl.fetch import fetch_section
        success = await fetch_section(mock_session, section, semaphore)
        assert success is True

@pytest.mark.asyncio
async def test_discover_all_manuals():
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={
        "results": [{"link": "/hmrc-internal-manuals/VAT", "title": "VAT"}],
        "total": 1
    })
    mock_session.get.return_value.__aenter__.return_value = mock_resp
    
    manuals = await discover_all_manuals(mock_session)
    assert len(manuals) == 1
    assert manuals[0]["slug"] == "VAT"

@pytest.mark.asyncio
async def test_get_manual_sections():
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={
        "details": {
            "body": "Some content",
            "section_id": "VIT123",
            "child_section_groups": []
        },
        "title": "Section Title",
        "public_updated_at": "2024-01-01"
    })
    mock_session.get.return_value.__aenter__.return_value = mock_resp
    
    semaphore = AsyncMock()
    sections = await get_manual_sections(mock_session, "VAT", "VAT Manual", semaphore)
    assert len(sections) == 1
    assert sections[0]["section_id"] == "VIT123"

@pytest.mark.asyncio
async def test_discover_all_cached():
    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data='[{"id": 1}]')):
        sections = await discover_all()
        assert len(sections) == 1

@pytest.mark.asyncio
async def test_fetch_section_success():
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={"data": "test"})
    mock_session.get.return_value.__aenter__.return_value = mock_resp
    
    section = {"manual_slug": "VAT", "section_id": "VIT123", "base_path": "/vat/vit123"}
    semaphore = AsyncMock()
    
    with patch("os.makedirs"), patch("os.path.exists", return_value=False), patch("builtins.open", mock_open()):
        success = await fetch_section(mock_session, section, semaphore)
        assert success is True

@pytest.mark.asyncio
async def test_fetch_all():
    sections = [{"manual_slug": "VAT", "section_id": "VIT123", "base_path": "/vat/vit123"}]
    with patch("src.etl.fetch.fetch_section", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = True
        await fetch_all(sections)
        mock_fetch.assert_called_once()

@pytest.mark.asyncio
async def test_run_update_no_changes():
    with patch("src.etl.discover.discover_all", new_callable=AsyncMock) as mock_discover, \
         patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data='{"public_updated_at": "2024-01-01"}')):
        
        mock_discover.return_value = [{
            "manual_slug": "VAT",
            "section_id": "VIT123",
            "updated_at": "2024-01-01"
        }]
        
        await run_update()
        # Coverage check for "Everything is up to date." branch

@pytest.mark.asyncio
async def test_run_ingest():
    with patch("src.etl.discover.discover_all", new_callable=AsyncMock) as mock_discover, \
         patch("src.etl.fetch.fetch_all", new_callable=AsyncMock) as mock_fetch, \
         patch("src.etl.parse.parse_all") as mock_parse, \
         patch("src.etl.ingest.process_pipeline") as mock_pipeline:
        
        mock_discover.return_value = []
        mock_parse.return_value = []
        
        # This will exit early if discovery returns nothing
        await run_pipeline()

def test_load_save_state():
    from src.etl.ingest import load_state, save_state, STATE_FILE
    state = {"processed_sections": ["TEST1"]}
    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=json.dumps(state))), \
         patch("os.makedirs"):
        
        loaded = load_state()
        assert loaded == state
        
        with patch("builtins.open", mock_open()) as m_open:
            save_state(state)
            m_open.assert_called_with(STATE_FILE, "w")

@pytest.mark.asyncio
async def test_discover_all_no_cache():
    with patch("os.path.exists", return_value=False), \
         patch("src.etl.discover.discover_all_manuals", new_callable=AsyncMock) as mock_manuals, \
         patch("src.etl.discover.get_manual_sections", new_callable=AsyncMock) as mock_sections, \
         patch("builtins.open", mock_open()):
        
        mock_manuals.return_value = [{"slug": "VAT", "title": "VAT"}]
        mock_sections.return_value = [{"section_id": "VIT123"}]
        
        sections = await discover_all(force=True)
        assert len(sections) == 1
        mock_manuals.assert_called_once()

@pytest.mark.asyncio
async def test_fetch_section_retry():
    mock_session = MagicMock()
    mock_resp_fail = MagicMock()
    mock_resp_fail.status = 500
    mock_resp_success = MagicMock()
    mock_resp_success.status = 200
    mock_resp_success.json = AsyncMock(return_value={"test": "data"})
    
    mock_session.get.return_value.__aenter__.side_effect = [mock_resp_fail, mock_resp_success]
    
    section = {"manual_slug": "VAT", "section_id": "VIT123", "base_path": "/vat/vit123"}
    semaphore = AsyncMock()
    
    with patch("os.makedirs"), \
         patch("os.path.exists", return_value=False), \
         patch("builtins.open", mock_open()), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        
        from src.etl.fetch import fetch_section
        success = await fetch_section(mock_session, section, semaphore)
        assert success is True
        assert mock_session.get.call_count == 2

@pytest.mark.asyncio
async def test_run_update_with_changes():
    def exists_side_effect(path):
        if "raw_json" in path and path.endswith(".json") and "update_state" not in path:
            return True
        return False

    with patch("src.etl.discover.discover_all", new_callable=AsyncMock) as mock_discover, \
         patch("os.path.exists", side_effect=exists_side_effect), \
         patch("builtins.open", mock_open(read_data='{"public_updated_at": "2024-10-20T10:00:00Z"}')), \
         patch("src.etl.fetch.fetch_all", new_callable=AsyncMock), \
         patch("src.etl.parse.parse_all", return_value=[{"section_id": "VIT123", "text": "test"}]), \
         patch("src.etl.update.process_pipeline") as mock_pipeline, \
         patch("src.etl.update._load_update_state", return_value={"embedded_sections": []}), \
         patch("src.etl.update._save_update_state"), \
         patch("src.etl.update._clear_update_state"), \
         patch("os.remove"):
        
        mock_discover.return_value = [{
            "manual_slug": "VAT",
            "section_id": "VIT123",
            "updated_at": "2024-10-21T10:00:00Z"
        }]
        
        async def mock_gen(*args):
            yield [{"section_id": "VIT123"}]
        mock_pipeline.return_value = mock_gen()
        
        await run_update()
        mock_pipeline.assert_called()

