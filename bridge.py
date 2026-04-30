import asyncio
import json
import requests
from mcp import ClientSession
from mcp.client.sse import sse_client

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "gemma4:e4b"
MCP_SERVER_URL = "http://localhost:8000/sse"

async def chat(prompt):
    print(f"🔄 Connecting to MCP Server at {MCP_SERVER_URL}...")
    
    try:
        async with sse_client(MCP_SERVER_URL) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                print("✅ Connected successfully!")

                mcp_tools = await session.list_tools()

                ollama_tools = []
                for t in mcp_tools.tools:
                    ollama_tools.append({
                        "type": "function",
                        "function": {
                            "name": t.name,
                            "description": t.description,
                            "parameters": t.inputSchema
                        }
                    })

                payload = {
                    "model": MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "tools": ollama_tools
                }
                
                print("🧠 Sending prompt to Ollama...")
                response = requests.post(OLLAMA_URL, json=payload).json()
                
                if 'message' not in response:
                    print("Ollama Error:", response)
                    return

                message = response['message']

                if 'tool_calls' in message:
                    # SAFETY SORTER: Force 'write_to_word' to always be executed first
                    tool_calls = sorted(
                        message['tool_calls'], 
                        key=lambda x: 0 if x['function']['name'] == 'write_to_word' else 1
                    )

                    for tool in tool_calls:
                        name = tool['function']['name']
                        args = tool['function']['arguments']
                        print(f"\n--- AI is calling tool: {name} ---")
                        
                        result = await session.call_tool(name, arguments=args)
                        print(f"--- Result: {result.content[0].text} ---\n")
                else:
                    print(f"\nAI: {message['content']}\n")

    except Exception as e:
        print(f"\n❌ Connection Error: Ensure your server is running. ({str(e)})")

if __name__ == "__main__":
    user_input = input("Enter The Prompt: ")
    asyncio.run(chat(user_input))