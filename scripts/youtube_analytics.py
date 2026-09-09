import json
import os
from datetime import datetime, timezone
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "data" / "analytics_history.json"


def get_credentials():
    required = ["YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"]
    missing = [x for x in required if not os.environ.get(x, "").strip()]
    if missing:
        raise RuntimeError("Missing YouTube secrets: " + ", ".join(missing))

    # Do not pass scopes here. The refresh token is already bound to the
    # OAuth scopes granted during authorization.
    return Credentials(
        None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
    )


def discover_video_ids(youtube, channel_id):
    # Use the channel's uploads playlist instead of search.list. This is
    # cheaper, deterministic, and reliably returns videos belonging to the
    # configured channel.
    channel = youtube.channels().list(
        part="contentDetails,snippet",
        id=channel_id,
    ).execute()
    items = channel.get("items", [])
    if not items:
        raise RuntimeError(
            "YOUTUBE_CHANNEL_ID was not found. Check that the secret contains the correct channel ID."
        )

    uploads_playlist = items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
    if not uploads_playlist:
        raise RuntimeError("Could not find the channel uploads playlist.")

    video_ids = []
    page_token = None
    while len(video_ids) < 50:
        response = youtube.playlistItems().list(
            part="contentDetails,snippet",
            playlistId=uploads_playlist,
            maxResults=min(50, 50 - len(video_ids)),
            pageToken=page_token,
        ).execute()
        for item in response.get("items", []):
            video_id = item.get("contentDetails", {}).get("videoId")
            if video_id:
                video_ids.append(video_id)
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return video_ids


def collect():
    channel_id = os.environ.get("YOUTUBE_CHANNEL_ID", "").strip()
    if not channel_id:
        raise RuntimeError("Missing YouTube secret: YOUTUBE_CHANNEL_ID")

    youtube = build("youtube", "v3", credentials=get_credentials(), cache_discovery=False)
    try:
        video_ids = discover_video_ids(youtube, channel_id)
    except HttpError as exc:
        print("YouTube API error while discovering channel videos:")
        print(exc)
        raise RuntimeError(
            "YouTube API could not read the channel. The OAuth refresh token must have permission to read YouTube channel data."
        ) from exc

    if not video_ids:
        print("No YouTube videos found yet; analytics skipped.")
        return None

    details = youtube.videos().list(
        part="statistics,snippet",
        id=",".join(video_ids),
    ).execute()
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
    HISTORY.write_text(
        json.dumps(history[-1000:], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(records, ensure_ascii=False, indent=2))
    return records


if __name__ == "__main__":
    collect()
