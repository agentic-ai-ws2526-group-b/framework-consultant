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
    {"framework": "Google ADK (OSS)", "url": "https://google.github.io/adk-docs/"},
    {"framework": "LangChain", "url": "https://docs.langchain.com/oss/python/langchain/overview"},
    {"framework": "LangGraph", "url": "https://docs.langchain.com/oss/python/langgraph/overview"},
    {"framework": "LangGraph (Ref)", "url": "https://langchain-ai.github.io/langgraph/reference/"},
    {"framework": "n8n", "url": "https://docs.n8n.io/"},
    {"framework": "CrewAI", "url": "https://docs.crewai.com/"},
    {"framework": "Hugging Face Agents", "url": "https://huggingface.co/docs/transformers/agents"},
    {"framework": "OpenAI Swarm", "url": "https://github.com/openai/swarm"},
    {"framework": "AutoGPT", "url": "https://github.com/Significant-Gravitas/AutoGPT"},
    {"framework": "Zapier", "url": "https://zapier.com/help/"},
]

# >>> 2b. BEWERTUNGSMATRIX-BASISSCORES (0–5) PRO FRAMEWORK <<<
# WICHTIG: Hier trägst du deine “Framework-Basiswerte (0–5) pro Dimension” ein.
# Diese Zahlen sind die deterministische Grundlage für dein Ranking im Backend.
#
# D1 = Time-to-MVP
# D2 = Integration & Tools
# D3 = Knowledge / RAG / Memory
# D4 = Multi-Agent & Orchestrierung
# D5 = Flexibilität & Erweiterbarkeit
# D6 = Einsteigerfreundlichkeit & Doku
#
# Wenn du dir bei einem Framework unsicher bist: setze erstmal 3 (neutral).
FRAMEWORK_DIMS = {
    "Google ADK":         {"D1": 4, "D2": 4, "D3": 3, "D4": 4, "D5": 3, "D6": 3},
    "Google ADK (OSS)":   {"D1": 4, "D2": 4, "D3": 3, "D4": 4, "D5": 3, "D6": 3},
    "LangChain":          {"D1": 4, "D2": 5, "D3": 4, "D4": 3, "D5": 4, "D6": 4},
    "LangGraph":          {"D1": 3, "D2": 4, "D3": 3, "D4": 5, "D5": 4, "D6": 3},
    "LangGraph (Ref)":    {"D1": 3, "D2": 4, "D3": 3, "D4": 5, "D5": 4, "D6": 3},
    "n8n":                {"D1": 5, "D2": 4, "D3": 2, "D4": 2, "D5": 3, "D6": 4},
    "CrewAI":             {"D1": 4, "D2": 3, "D3": 3, "D4": 4, "D5": 3, "D6": 3},
    "Hugging Face Agents": {"D1": 3, "D2": 3, "D3": 3, "D4": 2, "D5": 3, "D6": 3},
    "OpenAI Swarm":       {"D1": 4, "D2": 3, "D3": 2, "D4": 4, "D5": 3, "D6": 2},
    "AutoGPT":            {"D1": 2, "D2": 3, "D3": 3, "D4": 3, "D5": 4, "D6": 2},
    "Zapier":             {"D1": 5, "D2": 5, "D3": 2, "D4": 2, "D5": 2, "D6": 5},
}

# >>> 3. HELFERFUNKTIONEN <<<

def fetch_page_text(url: str) -> str:
    """Lädt eine Seite und extrahiert grob den sichtbaren Text."""
    print(f"🔍 Lade: {url}")
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except Exception as e:
        print(f"❌ Fehler beim Laden von {url}: {e}")
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")

    # störende Tags entfernen
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator=" ")
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


def _md5_id(raw: str) -> str:
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _factsheet_doc(framework: str, url: str) -> str:
    dims = FRAMEWORK_DIMS.get(framework, {"D1": 3, "D2": 3, "D3": 3, "D4": 3, "D5": 3, "D6": 3})
    # Kurzer Text reicht – Hauptsache Metadaten enthalten D1..D6 deterministisch
    return (
        f"FRAMEWORK_FACTSHEET\n"
        f"Framework: {framework}\n"
        f"URL: {url}\n"
        f"D1(Time-to-MVP): {dims['D1']}/5\n"
        f"D2(Integrationen & Tools): {dims['D2']}/5\n"
        f"D3(Knowledge/RAG/Memory): {dims['D3']}/5\n"
        f"D4(Multi-Agent & Orchestrierung): {dims['D4']}/5\n"
        f"D5(Flexibilität & Erweiterbarkeit): {dims['D5']}/5\n"
        f"D6(Einsteigerfreundlichkeit & Doku): {dims['D6']}/5\n"
    )


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

        # 4b) EIN Factsheet pro Framework (für deterministisches Scoring)
        dims = FRAMEWORK_DIMS.get(framework, {"D1": 3, "D2": 3, "D3": 3, "D4": 3, "D5": 3, "D6": 3})
        facts_raw_id = f"{framework}-{url}-FACTSHEET"
        facts_id = _md5_id(facts_raw_id)

        all_ids.append(facts_id)
        all_docs.append(_factsheet_doc(framework, url))
        # WICHTIG: D1..D6 flach speichern (keine nested dicts)
        all_meta.append({
            "framework": framework,
            "url": url,
            "chunk_index": -1,
            "is_factsheet": True,
            "D1": int(dims.get("D1", 3)),
            "D2": int(dims.get("D2", 3)),
            "D3": int(dims.get("D3", 3)),
            "D4": int(dims.get("D4", 3)),
            "D5": int(dims.get("D5", 3)),
            "D6": int(dims.get("D6", 3)),
        })

    if all_ids:
        # upsert ist besser als add (kein Duplicate-Feuerwerk beim Neulaufen)
        if hasattr(collection, "upsert"):
            collection.upsert(
                ids=all_ids,
                documents=all_docs,
                metadatas=all_meta,
            )
            print(f"💾 Insgesamt {len(all_ids)} Dokumente (inkl. Factsheets) in Chroma upserted.")
        else:
            collection.add(
                ids=all_ids,
                documents=all_docs,
                metadatas=all_meta,
            )
            print(f"💾 Insgesamt {len(all_ids)} Dokumente (inkl. Factsheets) in Chroma gespeichert.")
    else:
        print("⚠️ Keine Dokumente zu speichern.")


if __name__ == "__main__":
    ingest()
