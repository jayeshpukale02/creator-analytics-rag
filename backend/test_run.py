from app.scrapers.youtube import get_youtube_data
from app.vector_pipeline import chunk_transcript, store_video_chunks_in_db

if __name__ == "__main__":
    print("--- 🎬 STARTING FULL INGESTION PIPELINE 🎬 ---")
    
    # 1. Fetch data using Day 1 logic
    yt_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ" # Use any valid video with captions
    print("Fetching video data from YouTube...")
    video_data = get_youtube_data(yt_url)
    
    print(f"Successfully scraped video by: {video_data['creator']}")
    
    # 2. Chunk text using Day 2 logic
    print("Splitting transcript into optimized context chunks...")
    chunks = chunk_transcript(
        transcript_text=video_data["transcript"],
        video_id=video_data["video_id"],
        platform=video_data["platform"]
    )
    print(f"Created {len(chunks)} target metadata-tagged chunks.")
    
    # 3. Embed and upload to local Docker container
    print("Uploading vectorized tokens to local Qdrant container...")
    db_status = store_video_chunks_in_db(chunks)
    
    print("\n✅ PIPELINE SUCCESSFUL! Verification status:", db_status.status)