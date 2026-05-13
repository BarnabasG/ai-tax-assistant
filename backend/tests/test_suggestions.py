import asyncio
import sys
import json
from llm import router

async def main():
    messages = [
        {"role": "system", "content": "You are a tax assistant. Answer the query and at the very end, output exactly 3 suggested follow-up questions wrapped in <suggestions> tags separated by a pipe character |. Example: <suggestions>Q1|Q2|Q3</suggestions>"},
        {"role": "user", "content": "What is the VAT fraction for motoring road fuel?"}
    ]
    model = "gpt-oss:120b-cloud" # or qwen3.5:9b
    
    full_text = ""
    async for chunk_json in router.stream_chat(messages, model):
        try:
            data = json.loads(chunk_json.strip())
            if "token" in data:
                tok = data["token"]
                full_text += tok
                print(tok, end="", flush=True)
        except Exception:
            pass
            
    print("\n\n--- Full Text ---")
    print(repr(full_text))

if __name__ == "__main__":
    asyncio.run(main())
