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
    caption = str(data.get("caption", "Dil Ki Diary"))
    hashtags = " ".join("#" + h for h in data.get("hashtags", [])[:8])
    title = str(data.get("hook", "Dil Ki Diary")).strip()[:92]
    if not title:
        title = "Dil Ki Diary"
    description = f"{caption}\n\n{hashtags}\n\n#Shorts #DilKiDiary"

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": [topic, "Hindi emotional", "Hindi diary", "shayari", "emotional shorts", "Dil Ki Diary"],
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
