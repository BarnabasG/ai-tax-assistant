import pytest
from unittest.mock import patch, mock_open, MagicMock
import os
from snapshot import export_snapshot, import_snapshot

def test_export_snapshot_success():
    with patch("requests.post") as mock_post, \
         patch("requests.get") as mock_get, \
         patch("os.makedirs"), \
         patch("builtins.open", mock_open()):
        
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {"result": {"name": "test.snap"}}
        mock_post.return_value = mock_post_resp
        
        mock_get_resp = MagicMock()
        mock_get_resp.raise_for_status.return_value = None
        mock_get_resp.iter_content.return_value = [b"data"]
        mock_get.return_value.__enter__.return_value = mock_get_resp
        
        export_snapshot()
        mock_post.assert_called()
        mock_get.assert_called()

def test_import_snapshot_success():
    with patch("os.path.exists", return_value=True), \
         patch("requests.post") as mock_post, \
         patch("builtins.open", mock_open(read_data=b"data")):
        
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp
        
        import_snapshot()
        mock_post.assert_called()

def test_import_snapshot_failure_status():
    with patch("os.path.exists", return_value=True), \
         patch("requests.post") as mock_post, \
         patch("sys.exit", side_effect=SystemExit) as mock_exit, \
         patch("builtins.open", mock_open(read_data=b"data")):
        
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Bad Request"
        mock_post.return_value = mock_resp
        
        with pytest.raises(SystemExit):
            import_snapshot()
        mock_exit.assert_called_once_with(1)

def test_export_snapshot_failure():
    with patch("requests.post") as mock_post, \
         patch("sys.exit", side_effect=SystemExit) as mock_exit:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Error"
        mock_post.return_value = mock_resp
        
        with pytest.raises(SystemExit):
            export_snapshot()
        mock_exit.assert_called_once_with(1)

def test_import_snapshot_no_file():
    with patch("os.path.exists", return_value=False), \
         patch("sys.exit", side_effect=SystemExit) as mock_exit:
        with pytest.raises(SystemExit):
            import_snapshot()
        mock_exit.assert_called_once_with(1)
