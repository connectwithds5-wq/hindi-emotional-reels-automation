import json
import os
from pathlib import Path
from google import genai

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
HISTORY_PATH = ROOT / "data" / "content_history.json"


def load_history():
    if not HISTORY_PATH.exists():
        return []
    return json.loads(HISTORY_PATH.read_text(encoding="utf-8")).get("items", [])


def save_history(items):
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps({"items": items[-100:]}, ensure_ascii=False, indent=2), encoding="utf-8")


def generate():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY secret is missing")

    history = load_history()
    recent = [x.get("hook", "") for x in history[-20:]]
    topic = CONFIG["topics"][len(history) % len(CONFIG["topics"])]

    prompt = f"""
Create ONE completely original Hindi emotional micro-story/poetry reel.
Topic: {topic}
Length: about 8-12 seconds when read naturally.
Style: intimate, simple, modern Hindi, emotionally sharp, highly relatable.
Do NOT copy famous shayari, songs, movie dialogues, quotes, or known writers.
Do NOT use emojis inside the reel text.
The reel should feel like a tiny story with a strong emotional turn.
Previous hooks to avoid repeating: {json.dumps(recent, ensure_ascii=False)}

Return ONLY valid JSON with these keys:
 hook: 1 short opening line
 lines: array of 2-4 short Hindi lines
 caption: Instagram/YouTube caption, 1-3 sentences
 keywords: array of 8-12 Hindi/English search keywords
 hashtags: array of 8-15 hashtags, no # needed
"""

    client = genai.Client(api_key=api_key)
    models = [CONFIG["model"]]
    lite_model = CONFIG.get("lite_model")
    if lite_model and lite_model not in models:
        models.append(lite_model)

    last_error = None
    response = None
    used_model = None

    for model in models:
        try:
            print(f"Trying Gemini model: {model}")
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config={"response_mime_type": "application/json"},
            )
            used_model = model
            break
        except Exception as exc:
            last_error = exc
            print(f"Model {model} failed: {exc}")
            if model != models[-1]:
                print(f"Falling back to Lite model: {lite_model}")

    if response is None:
        raise RuntimeError(f"All configured Gemini models failed. Last error: {last_error}")

    data = json.loads(response.text)
    data["topic"] = topic
    data["model_used"] = used_model
    data["hook"] = str(data["hook"]).strip()
    data["lines"] = [str(x).strip() for x in data["lines"]]
    data["caption"] = str(data["caption"]).strip()
    data["keywords"] = [str(x).strip() for x in data.get("keywords", [])]
    data["hashtags"] = [str(x).strip().lstrip("#") for x in data.get("hashtags", [])]

    history.append(data)
    save_history(history)
    return data


if __name__ == "__main__":
    print(json.dumps(generate(), ensure_ascii=False, indent=2))
