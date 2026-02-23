import hashlib
import os

import chromadb
import google.generativeai as genai

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
EMBED_BATCH_SIZE = 100

_client = chromadb.PersistentClient(path="./chroma_db")


def _collection_key(email: str, folder_id: str) -> str:
    return hashlib.md5(f"{email}:{folder_id}".encode()).hexdigest()


def _chunk(text: str) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        chunk = text[start:start + CHUNK_SIZE]
        if chunk.strip():
            chunks.append(chunk)
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def _chunk_sections(sections: list[dict]) -> list[dict]:
    """Chunk each section independently, preserving page_label.
    Chunking within section boundaries means page attribution is always exact.
    Returns [{text, page_label}].
    """
    result = []
    for section in sections:
        page_label = section.get("page_label")
        for chunk in _chunk(section["text"]):
            result.append({"text": chunk, "page_label": page_label})
    return result


def _embed(texts: list[str], task_type: str = "retrieval_document") -> list[list[float]]:
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[i:i + EMBED_BATCH_SIZE]
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=batch,
            task_type=task_type,
        )
        all_embeddings.extend(result["embedding"])
    return all_embeddings


def index_files(email: str, folder_id: str, file_contents: list[dict]) -> None:
    """Chunk, embed, and upsert all file contents into ChromaDB."""
    key = _collection_key(email, folder_id)
    try:
        _client.delete_collection(key)
    except Exception:
        pass
    collection = _client.create_collection(key)

    ids: list[str] = []
    texts: list[str] = []
    metadatas: list[dict] = []

    for fc in file_contents:
        sections = fc.get("sections") or [{"text": fc["content"], "page_label": None}]
        for i, chunk_info in enumerate(_chunk_sections(sections)):
            ids.append(f"{fc['id']}_{i}")
            texts.append(chunk_info["text"])
            metadatas.append({
                "file_id": fc["id"],
                "file_name": fc["name"],
                "page_label": chunk_info["page_label"] or "",
            })

    if not texts:
        return

    embeddings = _embed(texts)
    collection.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)


def search(email: str, folder_id: str, query: str, top_k: int = 5) -> list[dict]:
    """Return top-K relevant chunks for the query."""
    key = _collection_key(email, folder_id)
    try:
        collection = _client.get_collection(key)
    except Exception:
        return []

    count = collection.count()
    if count == 0:
        return []

    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
    query_embedding = genai.embed_content(
        model="models/text-embedding-004",
        content=query,
        task_type="retrieval_query",
    )["embedding"]

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(top_k, count),
    )

    return [
        {
            "file_id": results["metadatas"][0][i]["file_id"],
            "file_name": results["metadatas"][0][i]["file_name"],
            "page_label": results["metadatas"][0][i].get("page_label") or None,
            "passage": results["documents"][0][i],
        }
        for i in range(len(results["ids"][0]))
    ]
