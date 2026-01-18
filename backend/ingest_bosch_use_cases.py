import os
import json
import chromadb
from dotenv import load_dotenv

load_dotenv()

CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db")
JSON_PATH = os.getenv("BOSCH_USECASES_JSON", "./data/bosch_use_cases.json")
COLLECTION_NAME = os.getenv("BOSCH_USECASES_COLLECTION", "bosch_use_cases")

def build_document(uc: dict) -> str:
    # Ein konsistenter Textblock, der gut für semantische Suche funktioniert
    parts = [
        f"Agent: {uc.get('agent_name','')}",
        f"Description: {uc.get('use_case_description','')}",
        f"Inputs: {', '.join(uc.get('inputs', []) or [])}",
        f"Outputs: {', '.join(uc.get('outputs', []) or [])}",
        f"Benefits: {', '.join(uc.get('benefits', []) or [])}",
        f"Limitations: {', '.join(uc.get('limitations', []) or [])}",
        f"Evidence: {uc.get('evidence','')}",
        f"Tags: {', '.join(uc.get('tags', []) or [])}",
    ]
    return "\n".join([p for p in parts if p and p.strip()])

def main():
    if not os.path.exists(JSON_PATH):
        raise FileNotFoundError(f"JSON nicht gefunden: {JSON_PATH}")

    with open(JSON_PATH, "r", encoding="utf-8") as f:
        payload = json.load(f)

    use_cases = payload.get("use_cases", [])
    if not use_cases:
        raise RuntimeError("Keine use_cases in der JSON gefunden.")

    chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    col = chroma_client.get_or_create_collection(COLLECTION_NAME)

    # Collection leeren: in Chroma v2 NICHT delete(where={})!
    # Stattdessen alles anhand IDs löschen (safe approach).
    existing = col.get(include=[])
    existing_ids = existing.get("ids", []) or []
    if existing_ids:
        col.delete(ids=existing_ids)

    ids = []
    documents = []
    metadatas = []

    for uc in use_cases:
        uc_id = uc.get("id")
        if not uc_id:
            continue

        ids.append(uc_id)
        documents.append(build_document(uc))

        rec = uc.get("recommended_for", {}) or {}
        metadatas.append({
            "agent_name": uc.get("agent_name", ""),
            "domain": uc.get("domain", ""),
            "maturity": uc.get("maturity", "unknown"),
            "experience_level": rec.get("experience_level", "unknown"),
            "learning_preference": rec.get("learning_preference", "unknown"),
            "tags": ",".join(uc.get("tags", []) or [])
        })

    col.add(ids=ids, documents=documents, metadatas=metadatas)

    print("✅ Ingestion abgeschlossen.")
    print(f"Collection: {COLLECTION_NAME}")
    print(f"Einträge: {len(ids)}")
    print(f"CHROMA_PATH: {CHROMA_PATH}")

if __name__ == "__main__":
    main()
