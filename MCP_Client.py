import asyncio
import json
import requests
from contextlib import asynccontextmanager, AsyncExitStack
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from mcp import ClientSession
from mcp.client.sse import sse_client
import uvicorn

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "gemma4:e4b" # Adjust if you changed your model
MCP_SERVER_URL = "http://127.0.0.1:8000/sse"

# Global variables to hold the persistent connection
mcp_session = None
mcp_exit_stack = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """This connects to the Word Server ONCE when the API starts up."""
    global mcp_session, mcp_exit_stack
    print("\n[API] 🔄 Initializing global connection to Word Server...")
    mcp_exit_stack = AsyncExitStack()
    
    try:
        read, write = await mcp_exit_stack.enter_async_context(sse_client(MCP_SERVER_URL))
        mcp_session = await mcp_exit_stack.enter_async_context(ClientSession(read, write))
        await mcp_session.initialize()
        print("[API] ✅ Connected to Word Server successfully!\n")
        yield
    except Exception as e:
        print(f"[API] ❌ Failed to connect to Word Server: {e}")
        print("[API] ⚠️  Make sure word_server.py is running on port 8000!")
        yield
    finally:
        if mcp_exit_stack:
            await mcp_exit_stack.aclose()

# Pass the lifespan into FastAPI
app = FastAPI(lifespan=lifespan)

# Allow your frontend HTML file to talk to this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- NEW: ULTRA-SPECIFIC SYSTEM PROMPT ---
SYSTEM_PROMPT = """You are an elite, autonomous Document and Diagram Generator. You communicate with the user strictly through actions.
CRITICAL RULES:
1. NEVER output raw Mermaid code in your conversational text. Do not show the user your code.
2. If the user asks for a diagram/flowchart, execute the 'save_diagram_png' or 'insert_diagram' tool SILENTLY.
3. Do not ask the user clarifying questions about file formats. If they don't specify, default to a standalone PNG named 'diagram.png'.
4. Once you have successfully called the tools, your final response to the user must be EXTREMELY brief. 
   Example acceptable responses:
   - "✅ Word document created at [Path]"
   - "✅ Diagram created at [Path]"
   - "✅ Document and Flowchart have been successfully generated."
Do not explain your thought process."""

# Initialize memory with the system prompt
chat_history = [{"role": "system", "content": SYSTEM_PROMPT}]

class ChatRequest(BaseModel):
    prompt: str

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    global chat_history
    
    if not mcp_session:
        return {"response": "Error: Not connected to Word Server. Check your server terminals."}
    
    chat_history.append({"role": "user", "content": req.prompt})
    print(f"\n[API] Received prompt: {req.prompt}")
    
    try:
        mcp_tools = await mcp_session.list_tools()

        ollama_tools = []
        for t in mcp_tools.tools:
            ollama_tools.append({
                "type": "function",
                "function": {"name": t.name, "description": t.description, "parameters": t.inputSchema}
            })

        while True:
            payload = {
                "model": MODEL,
                "messages": chat_history,
                "stream": False,
                "tools": ollama_tools
            }
            
            print("[API] 🧠 AI is thinking...")
            
            response_obj = await asyncio.to_thread(requests.post, OLLAMA_URL, json=payload)
            response = response_obj.json()
            
            if 'message' not in response:
                return {"response": "Error communicating with Ollama."}

            message = response['message']
            chat_history.append(message)

            if 'tool_calls' in message:
                tool_calls = sorted(
                    message['tool_calls'], 
                    key=lambda x: 0 if x['function']['name'] == 'write_to_word' else 1
                )

                for tool in tool_calls:
                    name = tool['function']['name']
                    args = tool['function']['arguments']
                    print(f"[API] ⚡ Executing Tool: {name}")
                    
                    result = await mcp_session.call_tool(name, arguments=args)
                    result_text = result.content[0].text
                    
                    print(f"[API] 📤 Tool Result Received: {result_text}")
                    chat_history.append({
                        "role": "tool",
                        "content": result_text
                    })
                continue 
                
            else:
                print(f"[API] ✅ Returning final response to frontend:\n{message['content']}")
                return {"response": message['content']}

    except Exception as e:
        error_msg = f"Inference Error: {str(e)}"
        print(f"[API] ❌ {error_msg}")
        return {"response": error_msg}

if __name__ == "__main__":
    print("🚀 Starting Bridge API on http://127.0.0.1:8001")
    uvicorn.run("MCP_Client:app", host="127.0.0.1", port=8001, reload=True)