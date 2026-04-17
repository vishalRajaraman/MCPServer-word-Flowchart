import requests
import json
import subprocess

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "gemma4:e4b"  

def call_word_mcp(tool_name, args):
    mcp_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": args}
    }
    
    process = subprocess.Popen(
        ['python3', 'wordMCP.py'], 
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    stdout, stderr = process.communicate(input=json.dumps(mcp_request))
    
    if stderr.strip():
        print(f"\n[DEBUG] wordMCP.py stderr:\n{stderr.strip()}\n")
    
    if not stdout.strip():
        if stderr:
            return {"result": {"content": [{"text": f"Script Error: {stderr}"}]}}
        return {"result": {"content": [{"text": "Error: Script returned no output"}]}}

    return json.loads(stdout)

def chat(prompt):
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "write_to_word",
                    "description": """Create a structured Word document. 
- Use '**Page X: Title**' for sections. 
- Use Markdown style tables.
- ABSOLUTELY NO PLACEHOLDERS: Do NOT write text like '(Diagram will be inserted here)'.
- Title and Page 1 will automatically be placed together.""",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string", "description": "Full path including .docx extension"},
                            "content": {"type": "string", "description": "Text content for the doc"},
                            "title": {"type": "string", "description": "Optional title"}
                        },
                        "required": ["file_path", "content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "insert_diagram",
                    "description": """Generates an architectural diagram image using Mermaid.js. 
CRITICAL SYNTAX RULES (FAILURE TO FOLLOW WILL CRASH THE SYSTEM):
1. Use `graph TD`.
2. ALL node labels MUST be wrapped in double quotes. Example: A["Source Code"] --> B["Lexer"].
3. ABSOLUTELY NO TEXT ON ARROWS. You are FORBIDDEN from using the pipe `|` character for arrows. 
   - FATAL ERROR: A -->|tokens| B
   - CORRECT: A --> B
4. Put all descriptive text, including acronyms like (IR) or (AST), INSIDE the double-quoted node labels.""",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string", 
                                "description": "Must be the exact same file_path used in the write_to_word tool so they go to the same document."
                            },
                            "description": {
                                "type": "string", 
                                "description": "Raw Mermaid code. FORBIDDEN: `-->|text|`. REQUIRED: plain `-->` ONLY. Quote all nodes."
                            },
                            "caption": {"type": "string", "description": "Text to appear below the diagram"}
                        },
                        "required": ["file_path", "description"]
                    }
                }
            }
        ]
    }
    
    try:
        response = requests.post(OLLAMA_URL, json=payload).json()
        if 'message' not in response:
            print("Ollama Error:", response)
            return

        message = response['message']

        if 'tool_calls' in message:
            for tool in message['tool_calls']:
                name = tool['function']['name']
                args = tool['function']['arguments']
                print(f"--- AI is calling tool: {name} ---")
                
                result = call_word_mcp(name, args)
                print(f"--- Result: {result['result']['content'][0]['text']} ---")
        else:
            print(f"AI: {message['content']}")
            
    except Exception as e:
        print(f"Bridge Error: {str(e)}")

if __name__ == "__main__":
    user_input = input("Enter The Prompt: ")
    chat(user_input)