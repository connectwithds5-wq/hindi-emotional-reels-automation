import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
HISTORY = ROOT / "data" / "analytics_history.json"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def get_credentials():
    required = ["YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"]
    missing = [x for x in required if not os.environ.get(x)]
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
    upload_file = OUTPUT / "youtube_upload.json"
    if not upload_file.exists():
        print("No youtube_upload.json yet; analytics skipped.")
        return None

    video_id = json.loads(upload_file.read_text(encoding="utf-8")).get("video_id")
    if not video_id:
        return None

    youtube = build("youtube", "v3", credentials=get_credentials(), cache_discovery=False)
    details = youtube.videos().list(part="statistics,snippet", id=video_id).execute()
    items = details.get("items", [])
    if not items:
        print("Video not found; analytics skipped.")
        return None

    stats = items[0].get("statistics", {})
    record = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "video_id": video_id,
        "title": items[0].get("snippet", {}).get("title", ""),
        "views": int(stats.get("viewCount", 0)),
        "likes": int(stats.get("likeCount", 0)),
        "comments": int(stats.get("commentCount", 0)),
    }

    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    history = []
    if HISTORY.exists():
        history = json.loads(HISTORY.read_text(encoding="utf-8"))
    history.append(record)
    HISTORY.write_text(json.dumps(history[-500:], ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False))
    return record


if __name__ == "__main__":
    collect()
