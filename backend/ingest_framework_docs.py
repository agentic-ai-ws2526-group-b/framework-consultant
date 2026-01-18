import requests
from bs4 import BeautifulSoup
import textwrap
import hashlib
import chromadb
from chromadb.config import Settings

# >>> 1. CHROMA INITIALISIEREN <<<

# Falls du schon einen anderen Pfad benutzt, HIER anpassen:
client = chromadb.PersistentClient(path="./chroma_db")

collection = client.get_or_create_collection(
    name="framework_docs",
)

# >>> 2. DEINE FRAMEWORKS & LINKS <<<

FRAMEWORK_URLS = [
    {
        "framework": "Google ADK",
        "url": "https://docs.cloud.google.com/agent-builder/agent-development-kit/overview",
    },
    {
        "framework": "Google ADK (OSS)",
        "url": "https://google.github.io/adk-docs/",
    },
    {
        "framework": "LangChain",
        "url": "https://docs.langchain.com/oss/python/langchain/overview",
    },
    {
        "framework": "LangGraph",
        "url": "https://docs.langchain.com/oss/python/langgraph/overview",
    },
    {
        "framework": "LangGraph (Ref)",
        "url": "https://langchain-ai.github.io/langgraph/reference/",
    },
    {
        "framework": "n8n",
        "url": "https://docs.n8n.io/",
    },
    {
        "framework": "CrewAI",
        "url": "https://docs.crewai.com/",
    },
    {
        "framework": "Hugging Face Agents",
        "url": "https://huggingface.co/docs/transformers/agents",
    },
    {
        "framework": "OpenAI Swarm",
        "url": "https://github.com/openai/swarm",
    },
    {
        "framework": "AutoGPT",
        "url": "https://github.com/Significant-Gravitas/AutoGPT",
    },
    {
        "framework": "Zapier",
        "url": "https://zapier.com/help/",
    },
]


# >>> 3. HELFERFUNKTIONEN <<<

def fetch_page_text(url: str) -> str:
    """Lädt eine Seite und extrahiert grob den sichtbaren Text."""
    print(f"🔍 Lade: {url}")
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"❌ Fehler beim Laden von {url}: {e}")
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")

    # störende Tags entfernen
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator=" ")
    # Whitespace säubern
    text = " ".join(text.split())
    return text


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100):
    """Teilt Text in überlappende Chunks (für RAG geeignet)."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start += chunk_size - overlap
    return chunks


# >>> 4. HAUPTLOGIK: SCRAPEN + IN CHROMA SPEICHERN <<<

def ingest():
    all_ids = []
    all_docs = []
    all_meta = []

    for item in FRAMEWORK_URLS:
        framework = item["framework"]
        url = item["url"]

        text = fetch_page_text(url)
        if not text:
            continue

        chunks = chunk_text(text)

        print(f"✅ {framework}: {len(chunks)} Chunks erzeugt")

        for idx, chunk in enumerate(chunks):
            # Eindeutige ID
            raw_id = f"{framework}-{url}-{idx}"
            doc_id = hashlib.md5(raw_id.encode("utf-8")).hexdigest()

            all_ids.append(doc_id)
            all_docs.append(chunk)
            all_meta.append({
                "framework": framework,
                "url": url,
                "chunk_index": idx,
            })

    if all_ids:
        collection.add(
            ids=all_ids,
            documents=all_docs,
            metadatas=all_meta,
        )
        print(f"💾 Insgesamt {len(all_ids)} Chunks in Chroma gespeichert.")
    else:
        print("⚠️ Keine Dokumente zu speichern.")


if __name__ == "__main__":
    ingest()
