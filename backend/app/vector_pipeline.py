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


def initialize_qdrant_collection():
    """Creates the Qdrant collection configured for the newest Gemini dimensions."""
    # Force-delete the old layout if it exists to reset the size boundaries
    if qdrant_client.collection_exists(collection_name=COLLECTION_NAME):
        qdrant_client.delete_collection(collection_name=COLLECTION_NAME)
        print(f"Cleared old conflicting schemas from collection '{COLLECTION_NAME}'...")
        
    if not qdrant_client.collection_exists(collection_name=COLLECTION_NAME):
        # UPGRADE: Configured for gemini-embedding-2's default 3072 dimensions
        qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=3072, distance=Distance.COSINE),
        )
        print(f"Collection '{COLLECTION_NAME}' successfully created in Qdrant for Gemini Embedding 2!")


def store_video_chunks_in_db(processed_chunks: list[dict]):
    """Embeds chunks via Gemini and writes them directly into the local Qdrant container."""
    initialize_qdrant_collection()
    
    points = []
    for i, chunk in enumerate(processed_chunks):
        print(f"Generating Gemini vector embedding for chunk {i+1}/{len(processed_chunks)}...")
        
        # Call the new free Gemini embedding engine
        vector = get_embedding(chunk["text"])
        
        points.append(
            PointStruct(
                id=hash(chunk["metadata"]["chunk_id"]) % (10**10),
                vector=vector,
                payload={
                    "page_content": chunk["text"],
                    **chunk["metadata"]
                }
            )
        )
        
    operation_info = qdrant_client.upsert(
        collection_name=COLLECTION_NAME,
        wait=True,
        points=points
    )
    return operation_info