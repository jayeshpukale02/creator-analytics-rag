import os
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct
from google import genai
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

qdrant_client = QdrantClient(url="http://localhost:6333")

# Initialize Google GenAI Client
gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

COLLECTION_NAME = "creator_videos"

def chunk_transcript(transcript_text: str, video_id: str, platform: str) -> list[dict]:
    """Splits raw transcript string into tightly optimized semantic chunks."""
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=400,
        chunk_overlap=50,
        length_function=len,
        separators=["\n\n", "\n", " ", ""]
    )
    
    raw_chunks = text_splitter.split_text(transcript_text)
    
    processed_chunks = []
    for index, text in enumerate(raw_chunks):
        processed_chunks.append({
            "text": text,
            "metadata": {
                "chunk_id": f"{video_id}_chunk_{index}",
                "video_id": video_id,
                "platform": platform,
                "source_position": index
            }
        })
        
    return processed_chunks

#embeddings
def get_embedding(text: str, model="gemini-embedding-2"):
    """Generates a high-precision 3072-dimensional vector embedding using Google Gemini"""
    text = text.replace("\n", " ")
    response = gemini_client.models.embed_content(
        model=model,
        contents=text,
    )
    # Grab the clean array list from the fresh SDK response object
    return response.embeddings[0].values


def initialize_qdrant_collection(force_reset: bool = False):
    """
    Creates the Qdrant collection.
    force_reset=True: wipes and recreates (used by /api/ingest for a clean slate).
    force_reset=False: creates only if it doesn't already exist (safe default).
    """
    if force_reset and qdrant_client.collection_exists(collection_name=COLLECTION_NAME):
        qdrant_client.delete_collection(collection_name=COLLECTION_NAME)
        print(f"[Qdrant] Wiped old collection '{COLLECTION_NAME}' for fresh ingest.")

    if not qdrant_client.collection_exists(collection_name=COLLECTION_NAME):
        # (resloves gemini model version conflict) Configured for gemini-embedding-2's default 3072 dimensions
        qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=3072, distance=Distance.COSINE),
        )
        print(f"[Qdrant] Collection '{COLLECTION_NAME}' created (3072-dim, Cosine).")


def store_video_chunks_in_db(processed_chunks: list[dict], video_metadata: dict = None):
    """
    Embeds chunks via Gemini and upserts them into Qdrant.
    video_metadata: optional dict of video-level fields (views, likes, creator, etc.)
                    merged into every chunk's payload so the analytics node can read
                    real metrics directly from Qdrant without a separate store.
    """
    points = []
    for i, chunk in enumerate(processed_chunks):
        print(f"[Embed] Chunk {i+1}/{len(processed_chunks)} — video_id: {chunk['metadata']['video_id']}")

        vector = get_embedding(chunk["text"])

        # Base payload: the chunk text + its own metadata
        payload = {
            "page_content": chunk["text"],
            **chunk["metadata"]
        }

        # Merge in video-level metadata so analytics queries work from chunk payloads
        if video_metadata:
            payload.update(video_metadata)

        points.append(
            PointStruct(
                id=hash(chunk["metadata"]["chunk_id"]) % (10**10),
                vector=vector,
                payload=payload
            )
        )

    operation_info = qdrant_client.upsert(
        collection_name=COLLECTION_NAME,
        wait=True,
        points=points
    )
    print(f"[Qdrant] Upserted {len(points)} chunks — status: {operation_info.status}")
    return operation_info