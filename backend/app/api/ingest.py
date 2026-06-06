from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.scrapers.youtube import get_youtube_data
from app.scrapers.instagram import get_instagram_data
from app.vector_pipeline import chunk_transcript, store_video_chunks_in_db, initialize_qdrant_collection

router = APIRouter()


class IngestRequest(BaseModel):
    youtube_url: str
    instagram_url: str


@router.post("/api/ingest")
async def ingest_videos(payload: IngestRequest):
    """
    Core ingestion endpoint. Accepts one YouTube URL (Video A) and one Instagram URL (Video B).
    Scrapes metadata + transcript, chunks and embeds both, then stores in Qdrant.
    Every chunk carries the full video metadata in its payload so the analytics node
    can query it without a separate database.
    """

    # Wipe + recreate collection so every ingest starts clean
    initialize_qdrant_collection(force_reset=True)

    results = {}

    # ── Video A: YouTube ─
    try:
        yt_data = get_youtube_data(payload.youtube_url)

        chunks_a = chunk_transcript(
            transcript_text=yt_data["transcript"],
            video_id="A",
            platform="youtube"
        )

        # Strip the raw transcript from the metadata dict before embedding —
        # only the chunked text goes into Qdrant, not the entire transcript blob
        video_meta_a = {k: v for k, v in yt_data.items() if k != "transcript"}
        video_meta_a["video_label"] = "A"

        store_video_chunks_in_db(chunks_a, video_metadata=video_meta_a)

        results["video_A"] = {
            "status": "ingested",
            "label": "A",
            "platform": "youtube",
            "creator": yt_data.get("creator"),
            "views": yt_data.get("views"),
            "likes": yt_data.get("likes"),
            "comments": yt_data.get("comments"),
            "engagement_rate": yt_data.get("engagement_rate"),
            "follower_count": yt_data.get("follower_count"),
            "duration_secs": yt_data.get("duration"),
            "upload_date": yt_data.get("upload_date"),
            "hashtags": yt_data.get("hashtags", [])[:5],
            "chunks_stored": len(chunks_a),
            "transcript_preview": yt_data["transcript"][:300] + "..."
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"YouTube ingestion failed: {str(e)}"
        )

    # ── Video B: Instagram ──────────────────────────────────────────────────────
    try:
        ig_data = get_instagram_data(payload.instagram_url)

        chunks_b = chunk_transcript(
            transcript_text=ig_data["transcript"],
            video_id="B",
            platform="instagram"
        )

        video_meta_b = {k: v for k, v in ig_data.items() if k != "transcript"}
        video_meta_b["video_label"] = "B"

        store_video_chunks_in_db(chunks_b, video_metadata=video_meta_b)

        results["video_B"] = {
            "status": "ingested",
            "label": "B",
            "platform": "instagram",
            "creator": ig_data.get("creator"),
            "views": ig_data.get("views"),
            "likes": ig_data.get("likes"),
            "comments": ig_data.get("comments"),
            "engagement_rate": ig_data.get("engagement_rate"),
            "follower_count": ig_data.get("follower_count"),
            "duration_secs": ig_data.get("duration"),
            "upload_date": ig_data.get("upload_date"),
            "hashtags": ig_data.get("hashtags", [])[:5],
            "chunks_stored": len(chunks_b),
            "transcript_preview": ig_data["transcript"][:300] + "..."
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Instagram ingestion failed: {str(e)}"
        )

    return {
        "message": "Both videos ingested. RAG chatbot is ready to answer questions.",
        "total_chunks": results["video_A"]["chunks_stored"] + results["video_B"]["chunks_stored"],
        "videos": results
    }
