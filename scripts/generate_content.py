import json
import os
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
HISTORY_PATH = ROOT / "data" / "content_history.json"


def load_history():
    if not HISTORY_PATH.exists():
        return []
    return json.loads(HISTORY_PATH.read_text(encoding="utf-8")).get("items", [])


def save_history(items):
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(
        json.dumps({"items": items[-100:]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def call_gemini_rest(api_key, model, prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.9,
            "maxOutputTokens": 512,
        },
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini HTTP {exc.code}: {detail[:1200]}") from exc
    except Exception as exc:
        raise RuntimeError(f"Gemini REST request failed: {exc}") from exc

    payload = json.loads(raw)
    try:
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected Gemini response: {raw[:1500]}") from exc
    return json.loads(text)


def generate():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY secret is missing")

    history = load_history()
    recent = [x.get("hook", "") for x in history[-20:]]
    topic = CONFIG["topics"][len(history) % len(CONFIG["topics"])]

    prompt = f"""
Create ONE completely original Hindi emotional diary entry for a 10-second faceless reel.
Topic: {topic}

IMPORTANT WRITING STYLE:
- This must sound like something a real person would quietly write in their diary at night.
- Do NOT write it like a shayari, poem, quote card, motivational quote, or social-media caption.
- Use conversational, intimate Hindi with a natural emotional turn.
- Start with a strong but believable first line, then develop one tiny thought/moment, and finish with an emotional afterthought.
- Avoid generic phrases such as 'तुम मेरी जिंदगी हो', 'आज भी तुम्हारी याद आती है', 'सच्चा प्यार', etc. unless the context makes them genuinely fresh.
- The writing should feel specific and relatable, not dramatic for the sake of drama.

VISUAL CONSTRAINTS:
- The words will be placed on the blue ruled lines of a notebook page.
- Write exactly 4 or 5 short lines total.
- Aim for 4-7 Hindi words per line and 22-30 Hindi words total.
- Each line should read naturally on its own and should not be so long that it needs to wrap again.
- Do NOT create a separate headline/title. The first line is the beginning of the diary thought.
- Do NOT use emojis, quotation marks, labels, bullets, or English words inside the reel text.
- Do NOT copy famous shayari, songs, movie dialogues, quotes, or known writers.

Previous hooks to avoid repeating: {json.dumps(recent, ensure_ascii=False)}

Return ONLY valid JSON with these keys:
 hook: the first diary line
 lines: array containing 3-4 additional diary lines; hook + lines must be exactly 4-5 lines total
 caption: Instagram/YouTube caption, 1-3 sentences
 keywords: array of 8-12 Hindi/English search keywords
 hashtags: array of 8-15 hashtags, no # needed
"""

    models = []
    for key in ("model", "lite_model", "legacy_lite_model"):
        model = CONFIG.get(key)
        if model and model not in models:
            models.append(model)

    last_error = None
    data = None
    used_model = None

    for model in models:
        try:
            print(f"Trying Gemini REST model: {model}")
            data = call_gemini_rest(api_key, model, prompt)
            used_model = model
            print(f"Gemini model succeeded: {model}")
            break
        except Exception as exc:
            last_error = exc
            print(f"Model {model} failed: {exc}")
            if model != models[-1]:
                print("Trying next configured fallback model...")

    if data is None:
        raise RuntimeError(f"All configured Gemini models failed. Last error: {last_error}")

    data["topic"] = topic
    data["model_used"] = used_model
    data["hook"] = str(data["hook"]).strip()
    data["lines"] = [str(x).strip() for x in data["lines"]][:4]
    data["caption"] = str(data["caption"]).strip()
    data["keywords"] = [str(x).strip() for x in data.get("keywords", [])]
    data["hashtags"] = [str(x).strip().lstrip("#") for x in data.get("hashtags", [])]

    history.append(data)
    save_history(history)
    return data


if __name__ == "__main__":
    print(json.dumps(generate(), ensure_ascii=False, indent=2))
