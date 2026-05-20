import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.llm import LLMRouter

@pytest.fixture
def router():
    return LLMRouter()

@pytest.mark.parametrize("model_in, expected_backend, expected_model", [
    ("qwen3.5:9b", "ollama_local", "qwen3.5:9b"),
    ("remote/llama3", "ollama_remote", "llama3"),
    (None, "ollama_local", "mock-default"),
])
def test_resolve_model(router, model_in, expected_backend, expected_model):
    with patch("src.llm.DEFAULT_MODEL", "mock-default"):
        backend, model = router.resolve_model(model_in)
        assert backend == expected_backend
        assert model == expected_model

@pytest.mark.asyncio
async def test_get_available_models(router):
    with patch("aiohttp.ClientSession.get") as mock_get:
        # Mock local Ollama response
        mock_resp_local = MagicMock()
        mock_resp_local.status = 200
        mock_resp_local.json = AsyncMock(return_value={"models": [{"name": "local-model"}]})
        
        mock_get.return_value.__aenter__.side_effect = [mock_resp_local]
        
        result = await router.get_available_models()
        assert any(m["id"] == "local-model" for m in result["models"])
        assert result["ollama_running"] is True

@pytest.mark.asyncio
async def test_stream_ollama_filtering(router):
    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status = 200
        
        # Simulated Ollama stream with <think> blocks
        chunks = [
            b'{"message": {"content": "Hello "}}',
            b'{"message": {"content": "<think> reasoning </think>"}}',
            b'{"message": {"content": "world"}}'
        ]
        mock_resp.content = AsyncMock()
        mock_resp.content.__aiter__.return_value = chunks
        
        mock_post.return_value.__aenter__.return_value = mock_resp
        
        tokens = []
        async for chunk_json in router._stream_ollama("url", "model", []):
            data = json.loads(chunk_json)
            if "token" in data:
                tokens.append(data["token"])
        
        full_text = "".join(tokens)
        assert "Hello" in full_text
        assert "world" in full_text
        assert "reasoning" not in full_text

@pytest.mark.asyncio
async def test_stream_chat_local(router):
    with patch.object(router, "_stream_ollama") as mock_stream:
        async def mock_gen(*args):
            yield '{"token": "hi"}'
        mock_stream.return_value = mock_gen()
        
        tokens = []
        async for token in router.stream_chat([], "qwen3.5:9b"):
            tokens.append(token)
            
        assert "hi" in tokens[0]

@pytest.mark.asyncio
async def test_get_available_models_remote(router):
    with patch("aiohttp.ClientSession.get") as mock_get, \
         patch("src.llm.OLLAMA_REMOTE_URL", "http://remote:11434"):
        
        mock_resp_local = MagicMock()
        mock_resp_local.status = 500 # Local down
        
        mock_resp_remote = MagicMock()
        mock_resp_remote.status = 200
        mock_resp_remote.json = AsyncMock(return_value={"models": [{"name": "remote-model"}]})
        
        mock_get.return_value.__aenter__.side_effect = [mock_resp_local, mock_resp_remote]
        
        result = await router.get_available_models()
        assert any(m["id"] == "remote/remote-model" for m in result["models"])

@pytest.mark.asyncio
async def test_stream_ollama_error(router):
    with patch("aiohttp.ClientSession.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status = 404
        mock_resp.text = AsyncMock(return_value="Model not found")
        mock_post.return_value.__aenter__.return_value = mock_resp
        
        tokens = []
        async for chunk_json in router._stream_ollama("url", "model", []):
            tokens.append(chunk_json)
            
        assert "error" in tokens[0]
        assert "404" in tokens[0]

@pytest.mark.asyncio
async def test_stream_chat_remote(router):
    with patch.object(router, "_stream_ollama") as mock_stream, \
         patch("src.llm.OLLAMA_REMOTE_URL", "http://remote:11434"):
        async def mock_gen(*args):
            yield '{"token": "remote hi"}'
        mock_stream.return_value = mock_gen()
        
        tokens = []
        async for token in router.stream_chat([], "remote/llama3"):
            tokens.append(token)
            
        assert "remote hi" in tokens[0]

@pytest.mark.asyncio
async def test_get_available_models_unreachable_no_models(router):
    with patch("aiohttp.ClientSession.get") as mock_get, \
         patch("src.llm.OLLAMA_REMOTE_URL", ""):
        mock_get.return_value.__aenter__.side_effect = Exception("Down")
        result = await router.get_available_models()
        assert result["ollama_running"] is False
        assert len(result["models"]) >= 1

@pytest.mark.asyncio
async def test_stream_chat_remote_no_url(router):
    with patch("src.llm.OLLAMA_REMOTE_URL", ""):
        tokens = []
        async for token in router.stream_chat([], "remote/llama3"):
            tokens.append(token)
        assert "not configured" in tokens[0]
