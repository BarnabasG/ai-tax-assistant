"""
LLM Router: Unified interface for local Ollama, remote Ollama, and Gemini API.
Supports streaming responses.
"""

import json
import os
from typing import AsyncGenerator

import aiohttp
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_REMOTE_URL = os.getenv("OLLAMA_REMOTE_URL", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DEFAULT_MODEL = os.getenv("DEFAULT_CHAT_MODEL", "qwen3.5:9b")


class LLMRouter:
    def __init__(self):
        # Only init Gemini if key is present
        self.gemini_client = None
        if GEMINI_API_KEY:
            self.gemini_client = genai.Client(api_key=GEMINI_API_KEY)

    def resolve_model(self, model_string: str) -> tuple[str, str]:
        """
        Resolves the model string to a backend and specific model name.
        Ollama handles cloud model routing natively (e.g. gpt-oss:120b-cloud
        is sent to localhost:11434 just like a local model).
        Example inputs:
        - "qwen3.5:9b"          -> ("ollama_local", "qwen3.5:9b")
        - "gpt-oss:120b-cloud"  -> ("ollama_local", "gpt-oss:120b-cloud")  # Ollama routes to cloud
        - "remote/llama3.1:70b" -> ("ollama_remote", "llama3.1:70b")
        - "gemini-2.5-flash"    -> ("gemini", "gemini-2.5-flash")
        """
        model_string = model_string or DEFAULT_MODEL

        if model_string.startswith("gemini"):
            return "gemini", model_string
        elif model_string.startswith("remote/"):
            return "ollama_remote", model_string.replace("remote/", "")
        else:
            # Local Ollama handles both local and cloud-routed models
            return "ollama_local", model_string

    async def _stream_ollama(self, url: str, model: str, messages: list[dict]) -> AsyncGenerator[str, None]:
        payload = {"model": model, "messages": messages, "stream": True}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{url}/api/chat", json=payload) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    yield json.dumps({"error": f"Ollama HTTP {resp.status}: {error}"})
                    return
                
                # Track whether we're inside a <think>...</think> reasoning block.
                # Thinking models (qwen3, gpt-oss etc.) emit these before their answer
                # and we don't want to stream them to the frontend.
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

    async def _stream_gemini(self, model: str, messages: list[dict]) -> AsyncGenerator[str, None]:
        if not self.gemini_client:
            yield json.dumps({"error": "GEMINI_API_KEY not configured"})
            return

        # Convert OpenAI/Ollama message format to Gemini format
        # Gemini expects alternating user/model turns, and system instructions separately
        system_instruction = None
        gemini_contents = []
        
        for msg in messages:
            if msg["role"] == "system":
                system_instruction = msg["content"]
            elif msg["role"] == "user":
                gemini_contents.append(types.Content(role="user", parts=[types.Part.from_text(msg["content"])]))
            elif msg["role"] == "assistant":
                gemini_contents.append(types.Content(role="model", parts=[types.Part.from_text(msg["content"])]))

        config = types.GenerateContentConfig()
        if system_instruction:
            config.system_instruction = system_instruction

        try:
            # We must run this synchronous generator in an executor if the SDK is blocking,
            # but the new google-genai SDK has async support via client.aio
            response_stream = await self.gemini_client.aio.models.generate_content_stream(
                model=model,
                contents=gemini_contents,
                config=config
            )
            
            async for chunk in response_stream:
                if chunk.text:
                    yield json.dumps({"token": chunk.text})
                    
        except Exception as e:
            yield json.dumps({"error": f"Gemini API error: {str(e)}"})

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
        elif backend == "gemini":
            async for token in self._stream_gemini(specific_model, messages):
                yield token + "\n\n"

router = LLMRouter()
