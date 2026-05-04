import os
import requests
import re
from dotenv import load_dotenv
from ddgs import DDGS
from pinecone import Pinecone, ServerlessSpec
from sentence_transformers import SentenceTransformer

# ==========================================
# 1. SETUP & CONFIGURATION
# ==========================================
load_dotenv()
PINECONE_API_KEY = os.getenv("pinecone_key")

if not PINECONE_API_KEY:
    raise ValueError("🚨 Missing PINECONE_API_KEY! Check your .env file.")

INDEX_NAME = "web-research-test"

print("⏳ Loading local embedding model (this takes a few seconds)...")
model = SentenceTransformer('all-MiniLM-L6-v2') 

print("🔌 Connecting to Pinecone...")
pc = Pinecone(api_key=PINECONE_API_KEY)

if INDEX_NAME not in pc.list_indexes().names():
    print(f"🏗️  Creating new Pinecone index '{INDEX_NAME}'...")
    pc.create_index(
        name=INDEX_NAME,
        dimension=384,
        metric="cosine", 
        spec=ServerlessSpec(cloud="aws", region="us-east-1")
    )

index = pc.Index(INDEX_NAME)

# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================
def clean_scraped_text(markdown_text):
    """Aggressively removes links, images, URLs, and formatting cruft."""
    text = markdown_text
    
    # 1. Remove Markdown images: ![Alt Text](http://...)
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    # 2. Replace Markdown links with just their text: [Kotaku](http://...) -> Kotaku
    text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)
    # 3. Remove raw standalone URLs
    text = re.sub(r'http[s]?://\S+', '', text)
    # 4. Remove Wikipedia-style bracket citations (e.g., [8], [12])
    text = re.sub(r'\[\d+\]', '', text)
    # 5. Remove Markdown headers (e.g., "## Title" -> "Title")
    text = re.sub(r'#+\s+', '', text)
    # 6. Remove formatting symbols: Asterisks (*), Carets (^), and Checkboxes (- [x])
    text = re.sub(r'[*^]', '', text)
    text = re.sub(r'-\s\[x\]', '', text)
    # 7. Strip underscores used for italics
    text = re.sub(r'_(.*?)_', r'\1', text)
    # 8. Compress multiple spaces
    text = re.sub(r' +', ' ', text)
    # 9. Compress empty lines
    text = re.sub(r'\n\s*\n', '\n', text).strip()
    
    return text

def chunk_text(text, chunk_size=250, overlap=50):
    """Splits a massive document into overlapping windows of words."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk:
            chunks.append(chunk)
    return chunks

# ==========================================
# 3. THE MAIN RAG PIPELINE
# ==========================================
def run_autonomous_rag(user_prompt):
    clean_query = user_prompt.replace("'", "").replace('"', "").strip()
    
    print(f"\n🔍 1. Searching DuckDuckGo for: '{clean_query}'...")
    search_results = DDGS().text(clean_query, max_results=3)
    
    if not search_results:
        print("❌ No search results found. Try a different query.")
        return

    full_text = None
    target_url = None
    
    print("\n🕷️  2. Attempting to scrape results (with Anti-Bot fallback)...")
    
    for index_num, result in enumerate(search_results):
        url = result['href']
        title = result['title']
        
        print(f"\n   [{index_num + 1}/3] Trying: {title}")
        print(f"   🔗 URL: {url}")
        
        jina_url = f"https://r.jina.ai/{url}"
        response = requests.get(jina_url, headers={"Accept": "text/markdown"}, timeout=20)
        
        if response.status_code == 200:
            text = response.text
            
            bad_phrases = ["Target URL returned error 403", "requiring CAPTCHA", "Just a moment..."]
            
            if any(phrase in text for phrase in bad_phrases):
                print("   ⚠️  BLOCKED: Site requested a CAPTCHA or returned 403. Moving to next link...")
                continue 
            
            if len(text) < 300:
                print("   ⚠️  WARNING: Page has very little text. Moving to next link...")
                continue
                
            # Clean the text immediately with the aggressive filter!
            full_text = clean_scraped_text(text)
            target_url = url
            print(f"   ✅ SUCCESS! Downloaded and cleaned {len(full_text)} characters of text.")
            break 
            
        else:
            print(f"   ❌ Scrape failed with status {response.status_code}. Moving to next...")

    if not full_text:
        print("\n❌ FATAL: All top 3 search results blocked the scraper. Aborting.")
        return
    
    print("\n🔪 3. Chunking the entire document...")
    chunks = chunk_text(full_text, chunk_size=250, overlap=50)
    print(f"✅ Document split into {len(chunks)} overlapping chunks.")
    
    print("\n🧠 4. Embedding text and Upserting to Pinecone...")
    embeddings = model.encode(chunks).tolist()
    
    vectors_to_upsert = []
    for i, (chunk, vector) in enumerate(zip(chunks, embeddings)):
        vectors_to_upsert.append({
            "id": f"chunk_{i}",
            "values": vector,
            "metadata": {"text": chunk, "source": target_url}
        })
        
    index.upsert(vectors=vectors_to_upsert)
    print("✅ All chunks securely stored in Vector DB.")
    
    print(f"\n🔎 5. Semantic Search querying database for: '{clean_query}'")
    question_vector = model.encode([clean_query]).tolist()[0]
    
    db_results = index.query(
        vector=question_vector,
        top_k=3,
        include_metadata=True
    )
    
    print("\n" + "="*60)
    print("🎯 TOP 3 MOST RELEVANT CHUNKS RETRIEVED:")
    print("="*60)
    
    for rank, match in enumerate(db_results['matches']):
        score = match['score']
        text = match['metadata']['text']
        print(f"\n🥇 RANK {rank + 1} [Relevance Score: {score:.4f}]")
        print(f"{text}")
        print("-" * 60)

    print("\n🧹 Cleaning up database...")
    index.delete(delete_all=True)
    print("✅ Done!")

if __name__ == "__main__":
    print("Welcome to the Autonomous RAG Test!")
    user_input = input("\nEnter your research prompt: ")
    run_autonomous_rag(user_input)