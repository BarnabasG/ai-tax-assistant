import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock, mock_open
from evaluate import run_evaluation

@pytest.mark.asyncio
async def test_run_evaluation():
    with patch("evaluate.embed_query", new_callable=AsyncMock) as mock_embed, \
         patch("evaluate.generate_sparse_vector") as mock_sparse, \
         patch("evaluate.store.hybrid_search") as mock_search, \
         patch("os.makedirs"), \
         patch("builtins.open", mock_open()):
        
        mock_embed.return_value = [0.1]
        mock_sparse.return_value = {}
        
        mock_hit = MagicMock()
        mock_hit.payload = {"section_id": "VIT13500"}
        mock_hit.score = 0.9
        mock_search.return_value = [mock_hit]
        
        await run_evaluation()
        
        mock_search.assert_called()
