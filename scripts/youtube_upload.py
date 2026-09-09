import json
import os
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def credentials():
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


def upload():
    video_path = OUTPUT / "latest_reel.mp4"
    metadata_path = OUTPUT / "latest_metadata.json"
    if not video_path.exists():
        raise FileNotFoundError(video_path)
    if not metadata_path.exists():
        raise FileNotFoundError(metadata_path)

    data = json.loads(metadata_path.read_text(encoding="utf-8"))
    title = str(data.get("youtube_title") or data.get("hook") or "Dil Ki Diary")[:100]
    description = str(data.get("youtube_description") or data.get("caption") or "")
    hashtags = data.get("hashtags", [])
    tags = [str(x).lstrip("#") for x in data.get("keywords", [])]
    if hashtags:
        description = (description.rstrip() + "\n\n" + " ".join("#" + str(x).lstrip("#") for x in hashtags)).strip()

    youtube = build("youtube", "v3", credentials=credentials(), cache_discovery=False)
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags[:30],
            "categoryId": "24",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
    result = youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute()
    video_id = result["id"]

    upload_meta = {
        "video_id": video_id,
        "youtube_url": f"https://www.youtube.com/shorts/{video_id}",
        "title": title,
    }
    (OUTPUT / "youtube_upload.json").write_text(json.dumps(upload_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"YouTube upload succeeded: {upload_meta['youtube_url']}")
    return upload_meta


if __name__ == "__main__":
    upload()
