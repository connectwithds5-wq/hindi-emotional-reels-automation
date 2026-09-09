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
            "temperature": 0.95,
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
    recent = [x.get("hook", "") for x in history[-30:]]
    topic = CONFIG["topics"][len(history) % len(CONFIG["topics"])]

    prompt = f"""
Create ONE completely original Hindi micro-diary entry for a 10-second faceless reel.
Topic: {topic}

CORE FEEL:
- It must feel like a private thought someone wrote in their notebook after a real moment.
- Think: one tiny real-life situation -> one realization -> one quiet emotional punch.
- The viewer should think: "ये तो मेरे साथ भी हुआ है।"
- Simple language is more important than poetic language.
- Make the final line land emotionally without becoming melodramatic.

DO NOT:
- Do not write a generic quote, shayari, poem, motivational line, or Instagram-caption style post.
- Do not use abstract filler such as "कुछ रिश्ते", "कुछ लोग", "वक्त सब सिखा देता है" as the main idea.
- Avoid overused phrases like "आज भी तुम्हारी याद आती है", "सच्चा प्यार", "तुम मेरी जिंदगी हो", "भूलना आसान नहीं" unless a very specific situation makes the wording genuinely fresh.
- Do not copy or imitate famous shayari, songs, movie dialogues, or known writers.
- Do not force rhyming.

GOOD STORY PATTERN:
Line 1: a specific everyday moment or action.
Line 2: what the person almost said/did/thought.
Line 3: a small realization or contradiction.
Line 4-5: the quiet emotional twist.

Example of the FEEL (do not copy it):
कल उसकी chat खोली थी,
कुछ लिखकर फिर मिटा दिया।
अजीब है ना...
अब उससे बात करने से ज्यादा,
खुद को रोकना मुश्किल लगता है।

VISUAL CONSTRAINTS:
- Exactly 4 or 5 short lines total.
- Each line must be 4-7 Hindi words where possible.
- Total reel text should be about 22-30 words.
- Each line must fit on ONE ruled notebook line; never make a line that needs wrapping.
- No separate headline/title. The first line is the diary entry itself.
- No emojis, quotation marks, bullets, labels, hashtags, or English words inside the reel text.
- Keep punctuation natural and minimal.

Previous opening lines to avoid repeating:
{json.dumps(recent, ensure_ascii=False)}

Return ONLY valid JSON with these keys:
{{
  "hook": "first diary line",
  "lines": ["3-4 additional diary lines"],
  "caption": "Instagram/YouTube caption, 1-3 natural sentences",
  "keywords": ["8-12 Hindi/English search keywords"],
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
