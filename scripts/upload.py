import json
import os
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / "output" / "latest_reel.mp4"
METADATA = ROOT / "output" / "latest_metadata.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def env_required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing GitHub secret: {name}")
    return value


def upload():
    required = ["YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"]
    missing = [name for name in required if not os.environ.get(name, "").strip()]
    if missing:
        print("YouTube upload skipped: OAuth secrets not configured yet")
        return None

    if not VIDEO.exists() or not METADATA.exists():
        raise FileNotFoundError("Generated reel or metadata is missing")

    data = json.loads(METADATA.read_text(encoding="utf-8"))
    creds = Credentials(
        token=None,
        refresh_token=env_required("YOUTUBE_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=env_required("YOUTUBE_CLIENT_ID"),
        client_secret=env_required("YOUTUBE_CLIENT_SECRET"),
        scopes=SCOPES,
    )

    youtube = build("youtube", "v3", credentials=creds)
    topic = str(data.get("topic", "Hindi emotional diary"))
    title = str(data.get("youtube_title", data.get("hook", "Dil Ki Diary"))).strip()[:100] or "Dil Ki Diary"
    description = str(data.get("youtube_description", data.get("caption", "Dil Ki Diary"))).strip()
    hashtags = data.get("youtube_hashtags", data.get("hashtags", []))
    hashtags_text = " ".join("#" + str(h).lstrip("#") for h in hashtags[:10])
    if hashtags_text:
        description = f"{description}\n\n{hashtags_text}\n\n#Shorts #DilKiDiary"
    else:
        description = f"{description}\n\n#Shorts #DilKiDiary"

    generated_keywords = [str(x).strip() for x in data.get("youtube_keywords", []) if str(x).strip()]
    fallback_tags = [topic, "Hindi emotional", "Hindi diary", "emotional shorts", "Dil Ki Diary"]
    tags = list(dict.fromkeys(generated_keywords + fallback_tags))[:30]

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "22",
            "defaultLanguage": "hi",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(str(VIDEO), mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        _, response = request.next_chunk()

    video_id = response["id"]
    print(f"YouTube upload successful: https://www.youtube.com/shorts/{video_id}")
    return video_id


if __name__ == "__main__":
    upload()
