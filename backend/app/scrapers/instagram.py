import os
import re
import requests
import instaloader
from yt_dlp import YoutubeDL
from dotenv import load_dotenv

load_dotenv()

# Reuse a single Instaloader context (avoids repeated session overhead)
_loader = instaloader.Instaloader(
    download_pictures=False,
    download_videos=False,
    download_video_thumbnails=False,
    download_geotags=False,
    download_comments=False,
    save_metadata=False,
    quiet=True,
)


def _extract_shortcode(url: str) -> str:
    """Pull reel shortcode from any Instagram URL format."""
    m = re.search(r'/(?:reel|p)/([A-Za-z0-9_-]+)', url)
    return m.group(1) if m else ""


def get_instagram_data(url: str) -> dict:
    """
    Fetches Instagram Reel metadata.

    Priority:
      1. instaloader — public posts, no API key, returns views + followers
      2. yt-dlp      — fallback if instaloader rate-limits
      3. RapidAPI    — if RAPIDAPI_KEY present in .env
      4. Mock        — last resort so the app never crashes
    """

    shortcode = _extract_shortcode(url)

    # ── Strategy 1: instaloader ────────────────────────────────────────────────
    if shortcode:
        try:
            post = instaloader.Post.from_shortcode(_loader.context, shortcode)

            views     = post.video_view_count or 0
            likes     = post.likes            or 0
            comments  = post.comments         or 0
            followers = post.owner_profile.followers or 0
            caption   = post.caption          or ""

            # Engagement: prefer views as denominator, fall back to followers
            if views > 0:
                eng = round((likes + comments) / views * 100, 2)
            elif followers > 0:
                eng = round((likes + comments) / followers * 100, 2)
            else:
                eng = None

            duration = 0
            try:
                duration = int(post.video_duration or 0)
            except Exception:
                pass

            upload_date = ""
            try:
                upload_date = post.date_utc.strftime("%Y-%m-%d")
            except Exception:
                pass

            print(f"[Instagram] instaloader ✓ @{post.owner_username} | "
                  f"views={views} likes={likes} followers={followers}")

            return {
                "video_id":       shortcode,
                "platform":       "instagram",
                "creator":        post.owner_username,
                "follower_count": followers,
                "views":          views,
                "likes":          likes,
                "comments":       comments,
                "engagement_rate": eng,
                "duration":       duration,
                "upload_date":    upload_date,
                "hashtags":       [t for t in caption.split() if t.startswith('#')][:10],
                "transcript":     caption or "No caption available for this reel.",
            }
        except Exception as e:
            print(f"[Instagram] instaloader failed: {e} — trying yt-dlp…")

    # ── Strategy 2: yt-dlp ────────────────────────────────────────────────────
    try:
        ydl_opts = {'skip_download': True, 'quiet': True, 'no_warnings': True}
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        sc       = shortcode or info.get('id', 'unknown')
        views    = info.get('view_count')    or 0
        likes    = info.get('like_count')    or 0
        comments = info.get('comment_count') or 0
        followers= info.get('channel_follower_count') or 0
        caption  = info.get('description', '') or info.get('title', '') or ''

        if views > 0:
            eng = round((likes + comments) / views * 100, 2)
        elif followers > 0:
            eng = round((likes + comments) / followers * 100, 2)
        else:
            eng = None

        print(f"[Instagram] yt-dlp ✓ @{info.get('uploader','?')} views={views}")
        return {
            "video_id":       sc,
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
        print(f"[Instagram] yt-dlp failed: {e} — trying RapidAPI…")

    # ── Strategy 3: RapidAPI ──────────────────────────────────────────────────
    api_key = os.getenv("RAPIDAPI_KEY")
    if api_key and shortcode:
        try:
            r = requests.get(
                "https://instagram-scraper-api2.p.rapidapi.com/v1/post_info",
                headers={"X-RapidAPI-Key": api_key,
                         "X-RapidAPI-Host": "instagram-scraper-api2.p.rapidapi.com"},
                params={"code_or_id": shortcode},
                timeout=10
            )
            d = r.json().get('data', {})
            views    = d.get('view_count', 0)    or 0
            likes    = d.get('like_count', 0)    or 0
            comments = d.get('comment_count', 0) or 0
            followers= d.get('owner', {}).get('follower_count', 0) or 0
            caption  = d.get('caption', '') or ''
            eng = round((likes + comments) / views * 100, 2) if views > 0 else (
                  round((likes + comments) / followers * 100, 2) if followers > 0 else None)

            print(f"[Instagram] RapidAPI ✓ @{d.get('owner',{}).get('username','?')}")
            return {
                "video_id":       shortcode,
                "platform":       "instagram",
                "creator":        d.get('owner', {}).get('username', 'Unknown'),
                "follower_count": followers,
                "views":          views,
                "likes":          likes,
                "comments":       comments,
                "engagement_rate": eng,
                "duration":       d.get('video_duration', 0),
                "upload_date":    str(d.get('taken_at', '')),
                "hashtags":       [t for t in caption.split() if t.startswith('#')][:10],
                "transcript":     caption or "No caption available.",
            }
        except Exception as e:
            print(f"[Instagram] RapidAPI failed: {e} — using mock.")

    # ── Strategy 4: Mock fallback ─────────────────────────────────────────────
    print("[Instagram] All methods failed — using mock data.")
    return _mock_data()


def _mock_data() -> dict:
    return {
        "video_id":        "mock_reel_123",
        "platform":        "instagram",
        "creator":         "fitness_coach_mock",
        "follower_count":  45000,
        "views":           50000,
        "likes":           2200,
        "comments":        150,
        "engagement_rate": round((2200 + 150) / 50000 * 100, 2),
        "duration":        30,
        "upload_date":     "2026-05-01",
        "hashtags":        ["#gym", "#growth", "#motivation"],
        "transcript": (
            "In this video I'm going to show you the absolute best way to structure "
            "your morning routine for high energy. Step one is hydration. "
            "Stop reaching for coffee first thing in the morning."
        ),
    }

# Keep old name for any legacy references
get_mock_instagram_data = _mock_data