"""
LLM Router: Unified interface for local Ollama and remote Ollama.
Supports streaming responses.
"""

import asyncio
import json
import os
import time
from typing import AsyncGenerator, Optional

import aiohttp
from dotenv import load_dotenv

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_REMOTE_URL = os.getenv("OLLAMA_REMOTE_URL", "")
DEFAULT_MODEL = os.getenv("DEFAULT_CHAT_MODEL", "qwen3.5:9b")


class LLMRouter:
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._cache = None
        self._cache_time = 0
        self._cache_ttl = 5  # seconds

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def resolve_model(self, model_string: str) -> tuple[str, str]:
        """Resolves model string to backend and name."""
        model_string = model_string or DEFAULT_MODEL

        if model_string.startswith("remote/"):
            return "ollama_remote", model_string.replace("remote/", "")
        else:
            return "ollama_local", model_string

    async def fetch_ollama_models(self, url: str, provider: str) -> list[dict]:
        """Internal helper to fetch models from a specific Ollama instance."""
        try:
            session = await self._get_session()
            async with session.get(f"{url}/api/tags", timeout=2) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return [
                        {
                            "id": f"{'remote/' if provider == 'remote' else ''}{m['name']}",
                            "name": f"{m['name']}{' (Remote)' if provider == 'remote' else ''}",
                            "provider": provider
                        }
                        for m in data.get("models", [])
                    ]
        except Exception:
            pass
        return []

    async def get_available_models(self) -> dict:
        """Fetches available models from Ollama with caching and parallelism."""
        now = time.time()
        if self._cache and (now - self._cache_time) < self._cache_ttl:
            return self._cache

        tasks = [self.fetch_ollama_models(OLLAMA_URL, "local")]
        if OLLAMA_REMOTE_URL:
            tasks.append(self.fetch_ollama_models(OLLAMA_REMOTE_URL, "remote"))
        
        results = await asyncio.gather(*tasks)
        
        models = []
        for res in results:
            models.extend(res)
            
        ollama_running = any(m["provider"] == "local" for m in models)
        
        # Add Cloud Models if local Ollama is running or as a fixed set
        cloud_model_ids = [
            "gemma4:31b-cloud",
            "gemma3:12b-cloud",
            "gpt-oss:20b-cloud",
            "gpt-oss:120b-cloud",
        ]
        
        for cid in cloud_model_ids:
            # Create a human readable name from the ID
            base_name = cid.split(":")[0].replace("-", " ").title()
            if "Gpt" in base_name:
                base_name = base_name.replace("Gpt", "GPT").replace("Oss", "OSS")
            
            if cid == "gemma4:31b-cloud": name = "Gemma 4 31B"
            elif cid == "gemma3:12b-cloud": name = "Gemma 3 12B"
            elif cid == "gpt-oss:20b-cloud": name = "GPT-OSS 20B"
            elif cid == "gpt-oss:120b-cloud": name = "GPT-OSS 120B"
            else: name = base_name

            models.append({
                "id": cid,
                "name": name,
                "provider": "cloud"
            })

        if not models:
            # Absolute fallback
            models.append({"id": "qwen3.5:9b", "name": "Qwen3.5 9B", "provider": "local"})
            
        self._cache = {"models": models, "ollama_running": ollama_running}
        self._cache_time = now
        return self._cache

    async def _stream_ollama(self, url: str, model: str, messages: list[dict]) -> AsyncGenerator[str, None]:
        payload = {"model": model, "messages": messages, "stream": True}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{url}/api/chat", json=payload) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    yield json.dumps({"error": f"Ollama HTTP {resp.status}: {error}"})
                    return
                
                # Filter reasoning blocks if present
                in_think_block = False
                think_buffer = ""
                
                async for line in resp.content:
                    if line:
                        try:
                            data = json.loads(line.decode('utf-8'))
                            content = data.get("message", {}).get("content", "")
                            if not content:
                                continue
                            
                            # Accumulate and strip <think>...</think> blocks
                            think_buffer += content
                            out = ""
                            while True:
                                if in_think_block:
                                    end = think_buffer.find("</think>")
                                    if end == -1:
                                        think_buffer = ""  # still inside, discard
                                        break
                                    else:
                                        think_buffer = think_buffer[end + len("</think>"):]
                                        in_think_block = False
                                else:
                                    start = think_buffer.find("<think>")
                                    if start == -1:
                                        out += think_buffer
                                        think_buffer = ""
                                        break
                                    else:
                                        out += think_buffer[:start]
                                        think_buffer = think_buffer[start + len("<think>"):]
                                        in_think_block = True
                            
                            if out:
                                yield json.dumps({"token": out})
                        except json.JSONDecodeError:
                            pass

    async def stream_chat(self, messages: list[dict], model: str) -> AsyncGenerator[str, None]:
        """Main entry point for streaming chat."""
        backend, specific_model = self.resolve_model(model)
        
        if backend == "ollama_local":
            async for token in self._stream_ollama(OLLAMA_URL, specific_model, messages):
                yield token + "\n\n"
        elif backend == "ollama_remote":
            if not OLLAMA_REMOTE_URL:
                yield json.dumps({"error": "OLLAMA_REMOTE_URL not configured"}) + "\n\n"
                return
            async for token in self._stream_ollama(OLLAMA_REMOTE_URL, specific_model, messages):
                yield token + "\n\n"

router = LLMRouter()
