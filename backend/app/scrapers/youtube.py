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

    # 1. Fetch Transcript (using youtube-transcript-api v1.x API)
    try:
        api = YouTubeTranscriptApi()
        # Try English first, then fall back to any available language
        transcript_list = api.list(video_id)
        best_transcript = transcript_list.find_transcript(['en'])
        fetched = best_transcript.fetch()
        full_transcript = " ".join([snippet.text for snippet in fetched])
    except Exception:
        try:
            # Fallback: grab whatever language is available and auto-translate if possible
            api = YouTubeTranscriptApi()
            fetched = api.fetch(video_id)
            full_transcript = " ".join([snippet.text for snippet in fetched])
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