import sys
import json
import os
import requests
from io import BytesIO
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, Inches

def clean_mermaid(code):
    return code.replace("```mermaid", "").replace("```", "").strip()

def add_mermaid_diagram(doc, mermaid_code):
    url = "https://api.chartquery.com/v1/diagram"
    payload = {
        "diagram_type": "mermaid",
        "diagram_source": mermaid_code,
        "output_format": "png",
        "share": True
    }
    try:
        response = requests.post(url, json=payload, timeout=30)
        sys.stderr.write(f"API POST Status: {response.status_code}\n")
        
        if response.status_code == 200:
            api_data = response.json()
            render_url = api_data.get("render_url")
            
            if not render_url:
                sys.stderr.write(f"Error: JSON response missing 'render_url'. Body: {api_data}\n")
                return False
                
            sys.stderr.write(f"Successfully got URL: {render_url}\nFetching image...\n")
            img_response = requests.get(render_url, timeout=30)
            
            if img_response.status_code == 200 and 'image' in img_response.headers.get('Content-Type', ''):
                image_stream = BytesIO(img_response.content)
                
                # REVERTED: Back to 6.0 inches for maximum legibility. 
                # Word will automatically calculate the height to maintain aspect ratio.
                doc.add_picture(image_stream, width=Inches(6.0))
                
                last_p = doc.paragraphs[-1]
                last_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                return True
            else:
                sys.stderr.write(f"Error fetching image bytes. Content-Type: {img_response.headers.get('Content-Type')}\n")
                return False
        else:
            sys.stderr.write(f"API Error: {response.status_code}\nResponse: {response.text[:100]}\n")
            return False
            
    except Exception as e:
        sys.stderr.write(f"Diagram POST/GET Error: {str(e)}\n")
        return False

def create_or_edit_word(file_path, content=None, title=None, mermaid_code=None):
    try:
        if not file_path.lower().endswith('.docx'):
            file_path = os.path.splitext(file_path)[0] + ".docx"

        doc = Document(file_path) if os.path.exists(file_path) else Document()
        
        # 1. HEADER LOGIC
        if title:
            t = doc.add_heading(title, 0)
            t.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # 2. DIAGRAM LOGIC
        if mermaid_code:
            doc.add_heading("System Architecture Diagram", level=2)
            clean_code = clean_mermaid(mermaid_code)
            success = add_mermaid_diagram(doc, clean_code)
            
            if not success:
                doc.save(file_path)
                return "Error: Diagram API failed. The mermaid syntax might be invalid or the API is down."

        # 3. TEXT CONTENT LOGIC
        if content and isinstance(content, str) and content.strip():
            blocks = content.split('\n\n')
            for block in blocks:
                block = block.strip()
                if not block: continue

                # --- TABLE DETECTION ---
                if "|" in block and "\n" in block:
                    lines = block.split('\n')
                    if len([l for l in lines if '|' in l]) > 1:
                        rows = [l.split('|') for l in lines if '|' in l]
                        
                        table_data = []
                        for r in rows:
                            cleaned_row = [cell.strip() for cell in r]
                            if cleaned_row and cleaned_row[0] == '': cleaned_row.pop(0)
                            if cleaned_row and cleaned_row[-1] == '': cleaned_row.pop()
                            if not cleaned_row: continue
                            
                            is_separator = all(all(char in "-: " for char in cell) for cell in cleaned_row)
                            if not is_separator:
                                table_data.append(cleaned_row)
                        
                        if table_data:
                            max_cols = max(len(row) for row in table_data)
                            table = doc.add_table(rows=len(table_data), cols=max_cols)
                            table.style = 'Table Grid'
                            
                            for r_idx, row_data in enumerate(table_data):
                                for c_idx, val in enumerate(row_data):
                                    if c_idx < max_cols:
                                        cell = table.cell(r_idx, c_idx)
                                        p = cell.paragraphs[0]
                                        parts = val.split("**")
                                        for i, part in enumerate(parts):
                                            run = p.add_run(part)
                                            if i % 2 != 0: run.bold = True
                                        if r_idx == 0:
                                            for run in p.runs: run.bold = True
                            continue

                # --- PROCESS STANDARD TEXT ---
                lines = block.split('\n')
                for line in lines:
                    line = line.strip()
                    if not line: continue
                    
                    # Aggressive AI Artifact Filter
                    line_lower = line.lower()
                    if ("diagram" in line_lower and "inserted" in line_lower) or line.startswith("*(") or line == "*":
                        continue

                    # Page Breaks
                    if line.startswith("**Page ") or line.startswith("Page "):
                        if "Page 1" not in line: doc.add_page_break()
                        doc.add_heading(line.replace("**", ""), level=1)
                        continue
                        
                    # Markdown Headings
                    if line.startswith("### "):
                        doc.add_heading(line.replace("### ", "").replace("**", ""), level=3)
                        continue
                    elif line.startswith("## "):
                        doc.add_heading(line.replace("## ", "").replace("**", ""), level=2)
                        continue
                    elif line.startswith("# "):
                        doc.add_heading(line.replace("# ", "").replace("**", ""), level=1)
                        continue

                    # Bullet Points
                    if line.startswith("* ") or line.startswith("- "):
                        p = doc.add_paragraph(style='List Bullet')
                        line = line[2:].strip()
                    else:
                        p = doc.add_paragraph()

                    # Bolding Logic
                    parts = line.split("**")
                    for i, part in enumerate(parts):
                        run = p.add_run(part)
                        if i % 2 != 0: run.bold = True

        doc.save(file_path)
        return f"Success: Document updated at {os.path.abspath(file_path)}"
    except Exception as e:
        return f"Error: {str(e)}"

def main():
    line = sys.stdin.readline()
    if not line: return
    
    try:
        request = json.loads(line)
        params = request.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})

        result_text = ""
        if tool_name == "write_to_word":
            result_text = create_or_edit_word(
                file_path=args.get('file_path'), 
                content=args.get('content', ''), 
                title=args.get('title')
            )
        elif tool_name == "insert_diagram":
            result_text = create_or_edit_word(
                file_path=args.get('file_path'), 
                mermaid_code=args.get('description', '')
            )
        else:
            sys.stderr.write(f"Unknown tool: {tool_name}\n")
            return

        response = {
            "jsonrpc": "2.0", 
            "id": request.get("id"), 
            "result": {"content": [{"type": "text", "text": result_text}]}
        }
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()
        
    except Exception as e:
        sys.stderr.write(f"Fatal Script Error: {str(e)}\n")

if __name__ == "__main__":
    main()