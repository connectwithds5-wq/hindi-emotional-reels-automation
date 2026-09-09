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
            "temperature": 0.92,
            "maxOutputTokens": 700,
        },
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
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
    recent = [x.get("hook", "") for x in history[-30:]]
    topic = CONFIG["topics"][len(history) % len(CONFIG["topics"])]

    prompt = f"""
Write ONE completely original Hindi diary-style micro-story for the Dil Ki Diary page.
Topic: {topic}

CORE FORMULA — MUST FOLLOW:
1. SIMPLE: begin with an ordinary real-life moment.
2. RELATABLE: add a tiny detail people have actually experienced.
3. EMOTIONAL TWIST: end with a quiet realization that changes the meaning of the moment.

The reader should feel: "ये तो मेरे साथ भी हुआ है।"
It must sound like a private diary entry written by a normal person, not a poet performing for social media.

REAL-LIFE MOMENTS TO DRAW FROM:
- coming home from office and opening an old chat
- typing a message and deleting it
- seeing someone's birthday but not wishing them
- checking someone's last seen/status and pretending not to care
- finding an old photo while cleaning the phone
- sitting with family but mentally somewhere else
- a friend slowly becoming a stranger
- waiting for a reply that never comes
- being busy all day but thinking about one person at night
- choosing self-respect instead of sending one more message
- meeting someone after a long time and realizing things changed
- hearing an old song and remembering a specific day

WRITING RULES:
- Exactly 7 or 8 short lines total, with `hook` treated as line 1.
- Each line should be roughly 3-8 Hindi words.
- Total reel text around 35-55 Hindi words.
- Natural conversational Hindi. Keep it simple.
- One small concrete detail is better than dramatic words.
- Lines 1-3 should build the real-life moment.
- Lines 4-6 should reveal what the person is actually feeling.
- The last 1-2 lines MUST contain the emotional realization/twist.
- Do NOT make it a poem, shayari, motivational quote, generic quote card, or lecture.
- Do NOT use a separate title/headline.
- Do NOT use famous shayari, songs, movie dialogues, or copied quotes.
- Do NOT force rhyming.
- Avoid vague filler such as "कुछ लोग", "कुछ रिश्ते", "वक्त सब सिखा देता है" unless tied to a specific real moment.
- No emojis, quotation marks, bullets, labels, or English words inside the reel text.

Example of the FEEL only — DO NOT COPY:
कल उसकी chat खोली थी,
कुछ लिखकर फिर मिटा दिया।
अजीब है ना...
अब उससे बात करने से ज्यादा,
खुद को रोकना मुश्किल लगता है।

Previous openings to avoid repeating:
{json.dumps(recent, ensure_ascii=False)}

Return ONLY valid JSON:
{{
  "hook": "line 1",
  "lines": ["line 2", "line 3", "line 4", "line 5", "line 6", "line 7", "line 8"],
  "caption": "1-3 natural sentences for Instagram/YouTube",
  "keywords": ["8-12 search keywords"],
  "hashtags": ["8-15 hashtags without #"]
}}
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
    data["hook"] = str(data.get("hook", "")).strip()
    data["lines"] = [str(x).strip() for x in data.get("lines", [])][:7]
    data["caption"] = str(data.get("caption", "")).strip()
    data["keywords"] = [str(x).strip() for x in data.get("keywords", [])]
    data["hashtags"] = [str(x).strip().lstrip("#") for x in data.get("hashtags", [])]

    history.append(data)
    save_history(history)
    return data


if __name__ == "__main__":
    print(json.dumps(generate(), ensure_ascii=False, indent=2))
