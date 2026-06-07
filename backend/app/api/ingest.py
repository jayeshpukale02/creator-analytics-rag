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

        # IMPORTANT: exclude 'video_id' (raw YouTube ID like 'KHOSiaT4yC4') from the
        # metadata dict. The chunk already has video_id='A' set by chunk_transcript().
        # If we include the scraper's video_id here, payload.update() overwrites 'A'
        # with the raw ID, breaking all analytics queries that filter on video_id='A'.
        video_meta_a = {k: v for k, v in yt_data.items() if k not in ("transcript", "video_id")}
        video_meta_a["video_label"] = "A"
        video_meta_a["raw_video_id"] = yt_data.get("video_id", "")  # preserve for reference

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

        # Same fix: exclude raw 'video_id' so chunk's video_id='B' label is preserved.
        video_meta_b = {k: v for k, v in ig_data.items() if k not in ("transcript", "video_id")}
        video_meta_b["video_label"] = "B"
        video_meta_b["raw_video_id"] = ig_data.get("video_id", "")  # preserve for reference

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
