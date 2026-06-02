import re
from yt_dlp import YoutubeDL
from youtube_transcript_api import YouTubeTranscriptApi

def extract_youtube_id(url: str) -> str:
    """Extracts the 11-character video ID from any standard YouTube URL."""
    pattern = r'(?:v=|\/)([0-9A-Za-z_-]{11}).*'
    match = re.search(pattern, url)
    return match.group(1) if match else None

def get_youtube_data(url: str) -> dict:
    video_id = extract_youtube_id(url)
    if not video_id:
        raise ValueError("Invalid YouTube URL")

    # 1. Fetch Transcript
    # try:
    # # Get the list of available transcripts for the video ID
    #     transcript_list = YouTubeTranscriptApi().list(video_id)
    
    # # Find the best transcript available (automatically chooses English or fallback)
    #     best_transcript = transcript_list.find_transcript(['en'])
    
    # # Fetch the actual data chunks
    #     data_chunks = best_transcript.fetch()
    
    # # Combine chunks into a clean text string
    #     full_transcript = " ".join([t['text'] for t in data_chunks])
    # except Exception as e:
    #     full_transcript =(f"Transcript not available programmatically: {str(e)}"
    #     f"Reason: Subtitles might be disabled, or the scraper was throttled. Error: {str(e)}")
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        full_transcript = " ".join([t['text'] for t in transcript_list])
    except Exception as e:
        # Captures missing CC, private videos, or rate limits cleanly without crashing the app!
        full_transcript = (
            f"Transcript data could not be retrieved programmatically for this video. "
            f"Reason: Subtitles might be disabled, or the scraper was throttled. Error: {str(e)}"
        )
    # 2. Fetch Metadata via yt-dlp
    ydl_opts = {'skip_download': True, 'quiet': True,
    # adding this 'extractor_args' forces yt-dlp to bypass rigid runtime checks
    'extractor_args': {'youtube': {'player_client': ['default']}}}
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        
        views = info.get('view_count', 0)
        likes = info.get('like_count', 0)
        comments = info.get('comment_count', 0)
        
        # engagementt Formula: (likes + comments) / views * 100
        engagement_rate = ((likes + comments) / views * 100) if views > 0 else 0.0

        metadata = {
            "video_id": video_id,
            "platform": "youtube",
            "creator": info.get('uploader', 'Unknown'),
            "follower_count": info.get('channel_follower_count', 0),
            "views": views,
            "likes": likes,
            "comments": comments,
            "engagement_rate": round(engagement_rate, 2),
            "duration": info.get('duration', 0),
            "upload_date": info.get('upload_date', ''),
            "hashtags": info.get('tags', []),
            "transcript": full_transcript
        }
    return metadata