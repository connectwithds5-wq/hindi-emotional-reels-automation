import json
import os
from datetime import datetime, timezone
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "data" / "analytics_history.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


def get_credentials():
    required = ["YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"]
    missing = [x for x in required if not os.environ.get(x, "").strip()]
    if missing:
        raise RuntimeError("Missing YouTube secrets: " + ", ".join(missing))
    return Credentials(
        None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=SCOPES,
    )


def collect():
    channel_id = os.environ.get("YOUTUBE_CHANNEL_ID", "").strip()
    if not channel_id:
        raise RuntimeError("Missing YouTube secret: YOUTUBE_CHANNEL_ID")

    youtube = build("youtube", "v3", credentials=get_credentials(), cache_discovery=False)
    response = youtube.search().list(
        part="id",
        channelId=channel_id,
        type="video",
        order="date",
        maxResults=20,
    ).execute()
    video_ids = [x["id"]["videoId"] for x in response.get("items", []) if x.get("id", {}).get("videoId")]
    if not video_ids:
        print("No YouTube videos found yet; analytics skipped.")
        return None

    details = youtube.videos().list(part="statistics,snippet", id=",".join(video_ids)).execute()
    collected_at = datetime.now(timezone.utc).isoformat()
    records = []
    for item in details.get("items", []):
        stats = item.get("statistics", {})
        records.append({
            "collected_at": collected_at,
            "video_id": item["id"],
            "title": item.get("snippet", {}).get("title", ""),
            "published_at": item.get("snippet", {}).get("publishedAt", ""),
            "views": int(stats.get("viewCount", 0)),
            "likes": int(stats.get("likeCount", 0)),
            "comments": int(stats.get("commentCount", 0)),
        })

    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    history = []
    if HISTORY.exists():
        history = json.loads(HISTORY.read_text(encoding="utf-8"))
    history.extend(records)
    HISTORY.write_text(json.dumps(history[-1000:], ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(records, ensure_ascii=False, indent=2))
    return records


if __name__ == "__main__":
    collect()
