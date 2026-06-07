import os
import re
import requests
from yt_dlp import YoutubeDL
from dotenv import load_dotenv

load_dotenv()


def _extract_shortcode(url: str) -> str:
    """Pulls the reel shortcode from any Instagram URL format."""
    m = re.search(r'/reel/([A-Za-z0-9_-]+)', url)
    return m.group(1) if m else "unknown"


def get_instagram_data(url: str) -> dict:
    """
    Fetches Instagram Reel metadata + transcript.

    Strategy (in order):
      1. yt-dlp  — works for most public reels, no API key needed
      2. RapidAPI — if RAPIDAPI_KEY is set in .env
      3. Mock     — safe fallback so the rest of the app never crashes
    """

    # ── Strategy 1: yt-dlp (primary, no key required) ──────────────────────
    try:
        ydl_opts = {
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
            'extractor_args': {'instagram': {}},
        }
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        shortcode = _extract_shortcode(url) or info.get('id', 'unknown')
        views     = info.get('view_count') or 0
        likes     = info.get('like_count') or 0
        comments  = info.get('comment_count') or 0
        followers = info.get('channel_follower_count') or 0
        caption   = info.get('description', '') or info.get('title', '') or ''

        # Instagram often hides view_count. Fall back to likes/followers ratio.
        if views > 0:
            eng = round(((likes + comments) / views * 100), 2)
        elif followers > 0:
            eng = round(((likes + comments) / followers * 100), 2)
        elif likes + comments > 0:
            eng = None  # can't compute without a denominator
        else:
            eng = 0.0

        print(f"[Instagram] yt-dlp success: @{info.get('uploader','?')} | views={views} likes={likes}")
        return {
            "video_id":       shortcode,
            "platform":       "instagram",
            "creator":        info.get('uploader') or info.get('channel') or 'Unknown',
            "follower_count": followers,
            "views":          views,
            "likes":          likes,
            "comments":       comments,
            "engagement_rate": eng,
            "duration":       info.get('duration') or 0,
            "upload_date":    info.get('upload_date', ''),
            "hashtags":       [t for t in caption.split() if t.startswith('#')][:10],
            "transcript":     caption or "No caption available for this reel.",
        }
    except Exception as e:
        print(f"[Instagram] yt-dlp failed ({e}), trying RapidAPI…")

    # ── Strategy 2: RapidAPI (if key present) ──────────────────────────────
    api_key = os.getenv("RAPIDAPI_KEY")
    if api_key:
        try:
            shortcode = _extract_shortcode(url)
            if not shortcode or shortcode == "unknown":
                raise ValueError(f"Cannot extract shortcode from URL: {url!r}")

            response = requests.get(
                "https://instagram-scraper-api2.p.rapidapi.com/v1/post_info",
                headers={"X-RapidAPI-Key": api_key,
                         "X-RapidAPI-Host": "instagram-scraper-api2.p.rapidapi.com"},
                params={"code_or_id": shortcode},
                timeout=10
            )
            data = response.json().get('data', {})
            views    = data.get('view_count', 0) or 0
            likes    = data.get('like_count', 0) or 0
            comments = data.get('comment_count', 0) or 0
            eng      = round(((likes + comments) / views * 100), 2) if views > 0 else 0.0
            caption  = data.get('caption', '') or ''

            print(f"[Instagram] RapidAPI success: @{data.get('owner',{}).get('username','?')}")
            return {
                "video_id":      shortcode,
                "platform":      "instagram",
                "creator":       data.get('owner', {}).get('username', 'Unknown'),
                "follower_count":data.get('owner', {}).get('follower_count', 0),
                "views":         views,
                "likes":         likes,
                "comments":      comments,
                "engagement_rate": eng,
                "duration":      data.get('video_duration', 0),
                "upload_date":   str(data.get('taken_at', '')),
                "hashtags":      [t for t in caption.split() if t.startswith('#')][:10],
                "transcript":    caption or "No caption available.",
            }
        except Exception as e:
            print(f"[Instagram] RapidAPI failed ({e}), using mock…")

    # ── Strategy 3: Mock fallback ───────────────────────────────────────────
    print("[Instagram] Using mock data — add RAPIDAPI_KEY to .env or use a public reel URL.")
    return _mock_data()


def _mock_data() -> dict:
    return {
        "video_id":       "mock_reel_123",
        "platform":       "instagram",
        "creator":        "fitness_coach_mock",
        "follower_count": 45000,
        "views":          50000,
        "likes":          2200,
        "comments":       150,
        "engagement_rate": round(((2200 + 150) / 50000 * 100), 2),
        "duration":       30,
        "upload_date":    "2026-05-01",
        "hashtags":       ["#gym", "#growth", "#motivation"],
        "transcript":     (
            "In this video I'm going to show you the absolute best way to structure "
            "your morning routine for high energy. Step one is hydration. "
            "Stop reaching for coffee first thing in the morning."
        ),
    }

# Keep old name for any legacy references
get_mock_instagram_data = _mock_data