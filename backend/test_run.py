from app.scrapers.youtube import get_youtube_data
from app.scrapers.instagram import get_instagram_data

if __name__ == "__main__":
    print("--- TESTING YOUTUBE EXTRACTION ---")
    yt_url = "https://www.youtube.com/watch?v=tFxxQcsjBO0" # Replace with any real video
    yt_data = get_youtube_data(yt_url)
    print(f"Creator: {yt_data['creator']} | Engagement: {yt_data['engagement_rate']}%")
    print(f"Transcript Snippet: {yt_data['transcript'][:150]}...\n")

    print("--- TESTING INSTAGRAM EXTRACTION ---")
    ig_url = "https://www.instagram.com/p/DJjucBwy-IA/" 
    ig_data = get_instagram_data(ig_url)
    print(f"Creator: {ig_data['creator']} | Engagement: {ig_data['engagement_rate']}%")