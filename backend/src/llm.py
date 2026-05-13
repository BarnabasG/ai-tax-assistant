"""
LLM Router: Unified interface for local Ollama and remote Ollama.
Supports streaming responses.
"""

import json
import os
from typing import AsyncGenerator

import aiohttp
from dotenv import load_dotenv

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_REMOTE_URL = os.getenv("OLLAMA_REMOTE_URL", "")
DEFAULT_MODEL = os.getenv("DEFAULT_CHAT_MODEL", "qwen3.5:9b")


class LLMRouter:
    def __init__(self):
        pass

    def resolve_model(self, model_string: str) -> tuple[str, str]:
        """Resolves model string to backend and name."""
        model_string = model_string or DEFAULT_MODEL

        if model_string.startswith("remote/"):
            return "ollama_remote", model_string.replace("remote/", "")
        else:
            return "ollama_local", model_string

    async def get_available_models(self) -> dict:
        """Fetches available models from Ollama."""
        models = []
        ollama_running = False
        
        # 1. Local Ollama Models
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{OLLAMA_URL}/api/tags", timeout=2) as resp:
                    if resp.status == 200:
                        ollama_running = True
                        data = await resp.json()
                        for m in data.get("models", []):
                            name = m["name"]
                            models.append({
                                "id": name,
                                "name": name,
                                "provider": "local"
                            })
        except Exception:
            pass
            
        # 2. Remote Ollama Models
        if OLLAMA_REMOTE_URL:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{OLLAMA_REMOTE_URL}/api/tags", timeout=2) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for m in data.get("models", []):
                                name = m["name"]
                                models.append({
                                    "id": f"remote/{name}",
                                    "name": f"{name} (Remote)",
                                    "provider": "remote"
                                })
            except Exception:
                pass
                
        # 3. Cloud Models & Fallback
        if ollama_running:
            cloud_model_ids = [
                "gemma4:31b-cloud",
                "gemma3:12b-cloud",
                "gpt-oss:20b-cloud",
                "gpt-oss:120b-cloud",
            ]
            for cid in cloud_model_ids:
                # Create a human readable name from the ID
                # E.g. "kimi-k2.6:cloud" -> "Kimi K2.6"
                base_name = cid.split(":")[0].replace("-", " ").title()
                if "Gpt" in base_name:
                    base_name = base_name.replace("Gpt", "GPT").replace("Oss", "OSS")
                
                # Special cases for formatting
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
        else:
            # Fallback if Ollama is unreachable
            if not models:
                models.append({"id": "qwen3.5:9b", "name": "Qwen3.5 9B", "provider": "local"})
            
        return {"models": models, "ollama_running": ollama_running}

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
