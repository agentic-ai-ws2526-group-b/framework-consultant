import requests
from bs4 import BeautifulSoup
import hashlib
import chromadb

# >>> 1. CHROMA INITIALISIEREN <<<

client = chromadb.PersistentClient(path="./chroma_db")

collection = client.get_or_create_collection(
    name="framework_docs",
)

# >>> 2. DEINE FRAMEWORKS & LINKS <<<

FRAMEWORK_URLS = [
    {"framework": "Google ADK", "url": "https://docs.cloud.google.com/agent-builder/agent-development-kit/overview"},
    {"framework": "LangChain", "url": "https://docs.langchain.com/oss/python/langchain/overview"},
    {"framework": "LangGraph", "url": "https://docs.langchain.com/oss/python/langgraph/overview"},
    {"framework": "OpenAI Agents SDK", "url": "https://platform.openai.com/docs/overview"},
    {"framework": "Claude Agent SDK", "url": "https://platform.claude.com/docs/en/intro"},
    {"framework": "Cognigy", "url": "https://docs.cognigy.com"},
    {"framework": "n8n", "url": "https://docs.n8n.io"},
    {"framework": "CrewAI", "url": "https://docs.crewai.com"},
]

# >>> Allowlist (wichtig für Cleanup) <<<
ALLOWED_FRAMEWORKS = {item["framework"] for item in FRAMEWORK_URLS}

# >>> 2b. BEWERTUNGSMATRIX-BASISSCORES (0–5) PRO FRAMEWORK <<<

FRAMEWORK_DIMS = {
    "Google ADK":          {"D1": 4, "D2": 4, "D3": 3, "D4": 4, "D5": 3, "D6": 3},
    "LangChain":           {"D1": 4, "D2": 5, "D3": 4, "D4": 3, "D5": 4, "D6": 4},
    "LangGraph":           {"D1": 3, "D2": 4, "D3": 3, "D4": 5, "D5": 4, "D6": 3},
    "OpenAI Agents SDK":   {"D1": 4, "D2": 4, "D3": 3, "D4": 4, "D5": 4, "D6": 3},
    "Claude Agent SDK":    {"D1": 4, "D2": 4, "D3": 3, "D4": 3, "D5": 4, "D6": 3},
    "Cognigy":             {"D1": 4, "D2": 5, "D3": 3, "D4": 3, "D5": 3, "D6": 4},
    "n8n":                 {"D1": 5, "D2": 4, "D3": 2, "D4": 2, "D5": 3, "D6": 4},
    "CrewAI":              {"D1": 4, "D2": 3, "D3": 3, "D4": 4, "D5": 3, "D6": 3},
}

# >>> 3. HELFERFUNKTIONEN <<<

def _normalize_url(url: str) -> str:
    # sorgt für stabilere IDs (ohne trailing slash Unterschiede)
    return (url or "").strip().rstrip("/")

def fetch_page_text(url: str) -> str:
    """Lädt eine Seite und extrahiert grob den sichtbaren Text."""
    print(f"🔍 Lade: {url}")
    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except Exception as e:
        print(f"❌ Fehler beim Laden von {url}: {e}")
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")

    # störende Tags entfernen
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator=" ")
    return " ".join(text.split())

def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100):
    """Teilt Text in überlappende Chunks (für RAG geeignet)."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks

def _md5_id(raw: str) -> str:
    return hashlib.md5(raw.encode("utf-8")).hexdigest()

def _factsheet_doc(framework: str, url: str) -> str:
    dims = FRAMEWORK_DIMS.get(framework, {"D1": 3, "D2": 3, "D3": 3, "D4": 3, "D5": 3, "D6": 3})
    return (
        "FRAMEWORK_FACTSHEET\n"
        f"Framework: {framework}\n"
        f"URL: {url}\n"
        f"D1(Time-to-MVP): {dims['D1']}/5\n"
        f"D2(Integrationen & Tools): {dims['D2']}/5\n"
        f"D3(Knowledge/RAG/Memory): {dims['D3']}/5\n"
        f"D4(Multi-Agent & Orchestrierung): {dims['D4']}/5\n"
        f"D5(Flexibilität & Erweiterbarkeit): {dims['D5']}/5\n"
        f"D6(Einsteigerfreundlichkeit & Doku): {dims['D6']}/5\n"
    )

# >>> 3b. CLEANUP: alles löschen, was NICHT in der Allowlist ist <<<
def delete_not_allowed():
    got = collection.get(include=["metadatas"])  # <-- ids NICHT in include
    metas = got.get("metadatas", []) or []
    ids = got.get("ids", []) or []  # <-- ids kommen trotzdem im Response

    to_delete = []
    for i, meta in enumerate(metas):
        m = meta if isinstance(meta, dict) else {}
        fw = (m.get("framework") or "").strip()
        if fw and fw not in ALLOWED_FRAMEWORKS:
            if i < len(ids):
                to_delete.append(ids[i])

    if to_delete:
        collection.delete(ids=to_delete)
        print(f"🧹 {len(to_delete)} alte Framework-Dokumente gelöscht (nicht Allowlist).")
    else:
        print("🧹 Cleanup: nichts zu löschen.")

# >>> 4. HAUPTLOGIK: SCRAPEN + IN CHROMA SPEICHERN <<<

def ingest():
    # 1) Cleanup einmal pro Run
    delete_not_allowed()

    all_ids = []
    all_docs = []
    all_meta = []

    # 2) track factsheets, damit pro Framework genau 1 Factsheet existiert
    factsheet_added = set()

    for item in FRAMEWORK_URLS:
        framework = (item["framework"] or "").strip()
        url = _normalize_url(item["url"])

        text = fetch_page_text(url)
        if not text:
            continue

        chunks = chunk_text(text)
        print(f"✅ {framework}: {len(chunks)} Chunks erzeugt")

        # 4a) normale Doku-Chunks
        for idx, chunk in enumerate(chunks):
            raw_id = f"{framework}-{url}-{idx}"
            doc_id = _md5_id(raw_id)

            all_ids.append(doc_id)
            all_docs.append(chunk)
            all_meta.append({
                "framework": framework,
                "url": url,
                "chunk_index": idx,
                "is_factsheet": False,
            })

        # 4b) EIN Factsheet pro Framework (nicht pro URL)
        if framework not in factsheet_added:
            dims = FRAMEWORK_DIMS.get(framework, {"D1": 3, "D2": 3, "D3": 3, "D4": 3, "D5": 3, "D6": 3})
            facts_id = _md5_id(f"{framework}-FACTSHEET")  # stabil pro Framework

            all_ids.append(facts_id)
            all_docs.append(_factsheet_doc(framework, url))
            all_meta.append({
                "framework": framework,
                "url": url,            # referenz-url (erste gefundene)
                "chunk_index": -1,
                "is_factsheet": True,
                "D1": int(dims.get("D1", 3)),
                "D2": int(dims.get("D2", 3)),
                "D3": int(dims.get("D3", 3)),
                "D4": int(dims.get("D4", 3)),
                "D5": int(dims.get("D5", 3)),
                "D6": int(dims.get("D6", 3)),
            })
            factsheet_added.add(framework)

    if all_ids:
        if hasattr(collection, "upsert"):
            collection.upsert(ids=all_ids, documents=all_docs, metadatas=all_meta)
            print(f"💾 Insgesamt {len(all_ids)} Dokumente (inkl. Factsheets) in Chroma upserted.")
        else:
            collection.add(ids=all_ids, documents=all_docs, metadatas=all_meta)
            print(f"💾 Insgesamt {len(all_ids)} Dokumente (inkl. Factsheets) in Chroma gespeichert.")
    else:
        print("⚠️ Keine Dokumente zu speichern.")

if __name__ == "__main__":
    ingest()
