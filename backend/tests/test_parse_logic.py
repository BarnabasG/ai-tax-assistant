import pytest
import json
import os
from unittest.mock import patch, mock_open
from etl.parse import strip_html, parse_section

@pytest.mark.parametrize("html, expected", [
    ("<p>Hello</p><p>World</p>", "Hello\n\nWorld"),
    ("<ul><li>Item 1</li><li>Item 2</li></ul>", "- Item 1\n\n- Item 2"),
    ("Line 1<br>Line 2", "Line 1   Line 2"),
    ("   Multiple    spaces   ", "Multiple spaces"),
])
def test_strip_html(html, expected):
    assert strip_html(html).strip() == expected.strip()

def test_parse_section_success():
    mock_data = {
        "title": "VAT Manual - VIT123",
        "details": {
            "body": "<p>Content about VIT123 and related to [CG12345]. This content is now long enough to pass the quality filter of fifty characters.</p>",
            "breadcrumbs": [{"section_id": "VAT"}]
        },
        "base_path": "/manual/vat/vit123",
        "public_updated_at": "2024-01-01"
    }
    
    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=json.dumps(mock_data))):
        
        result = parse_section("vat-manual", "VIT123")
        
        assert result["section_id"] == "VIT123"
        assert "Content about VIT123" in result["text"]
        assert "CG12345" in result["related_pages"]
        assert "VAT" in result["breadcrumb"]
        assert result["tax_type"] == "VAT"

def test_parse_section_filter():
    # Content too short should be filtered out
    mock_data = {
        "title": "Short",
        "details": {"body": "<p>Too short</p>"},
        "base_path": "/short"
    }
    
    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=json.dumps(mock_data))):
        
        result = parse_section("vat-manual", "SHORT")
        assert result is None

def test_parse_all():
    sections = [{"manual_slug": "VAT", "section_id": "VIT123", "manual_title": "VAT"}]
    with patch("etl.parse.parse_section") as mock_parse_sec:
        mock_parse_sec.return_value = {"id": 1, "manual_slug": "VAT", "manual_title": "Old Title"}
        from etl.parse import parse_all
        result = parse_all(sections)
        assert len(result) == 1
        assert result[0]["manual_title"] == "VAT"
