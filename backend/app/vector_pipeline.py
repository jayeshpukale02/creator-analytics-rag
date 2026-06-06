import os
import uuid
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct
from google import genai
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

qdrant_client = QdrantClient(url="http://localhost:6333")
gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

COLLECTION_NAME = "creator_videos"


def chunk_transcript(transcript_text: str, video_id: str, platform: str) -> list[dict]:
    """Splits raw transcript into optimized semantic chunks tagged with video_id."""
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=400,
        chunk_overlap=50,
        length_function=len,
        separators=["\n\n", "\n", " ", ""]
    )
    raw_chunks = text_splitter.split_text(transcript_text)
    processed_chunks = []
    for index, text in enumerate(raw_chunks):
        chunk_id = f"{video_id}_chunk_{index}"
        processed_chunks.append({
            "text": text,
            "metadata": {
                "chunk_id": chunk_id,
                "video_id": video_id,
                "platform": platform,
                "source_position": index
            }
        })
    return processed_chunks


def get_embedding(text: str, model="gemini-embedding-2") -> list[float]:
    """Generates a 3072-dimensional Gemini embedding vector."""
    text = text.replace("\n", " ").strip()
    response = gemini_client.models.embed_content(model=model, contents=text)
    return response.embeddings[0].values


def initialize_qdrant_collection(force_reset: bool = False):
    """
    Creates the Qdrant collection.
    force_reset=True  → wipe + recreate (used on every /api/ingest call).
    force_reset=False → create only if missing (safe default).
    """
    if force_reset and qdrant_client.collection_exists(collection_name=COLLECTION_NAME):
        qdrant_client.delete_collection(collection_name=COLLECTION_NAME)
        print(f"[Qdrant] Wiped old collection '{COLLECTION_NAME}'.")

    if not qdrant_client.collection_exists(collection_name=COLLECTION_NAME):
        qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=3072, distance=Distance.COSINE),
        )
        print(f"[Qdrant] Collection '{COLLECTION_NAME}' created (3072-dim, Cosine).")


def store_video_chunks_in_db(processed_chunks: list[dict], video_metadata: dict = None):
    """
    Embeds each chunk with Gemini and upserts into Qdrant.
    video_metadata is merged into every chunk payload so the analytics node
    can read views/likes/engagement_rate directly from Qdrant — no separate DB needed.

    Uses uuid5 for deterministic, collision-safe, always-positive point IDs
    instead of Python's hash() which is non-deterministic across processes.
    """
    points = []
    for i, chunk in enumerate(processed_chunks):
        chunk_id = chunk["metadata"]["chunk_id"]
        print(f"[Embed] {i+1}/{len(processed_chunks)} — {chunk_id}")

        vector = get_embedding(chunk["text"])

        # Deterministic UUID → integer ID (uuid5 is stable across processes)
        point_id = uuid.uuid5(uuid.NAMESPACE_DNS, chunk_id).int >> 64  # 64-bit positive int

        payload = {
            "page_content": chunk["text"],
            **chunk["metadata"]
        }
        if video_metadata:
            payload.update(video_metadata)

        points.append(PointStruct(id=point_id, vector=vector, payload=payload))

    result = qdrant_client.upsert(
        collection_name=COLLECTION_NAME,
        wait=True,
        points=points
    )
    print(f"[Qdrant] Upserted {len(points)} chunks — status: {result.status}")
    return result