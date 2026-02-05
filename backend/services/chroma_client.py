# services/chroma_client.py
import os
import chromadb
from dotenv import load_dotenv

load_dotenv()

CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db")

def get_chroma_client() -> chromadb.PersistentClient:
    return chromadb.PersistentClient(path=CHROMA_PATH)

def get_collections(client: chromadb.PersistentClient):
    usecase_collection = client.get_or_create_collection("bosch_use_cases")
    framework_collection = client.get_or_create_collection("framework_docs")
    return usecase_collection, framework_collection
