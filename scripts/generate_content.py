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
    HISTORY_PATH.write_text(json.dumps({"items": items[-100:]}, ensure_ascii=False, indent=2), encoding="utf-8")


def call_gemini_rest(api_key, model, prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.95, "maxOutputTokens": 700},
    }
    request = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                     headers={"x-goog-api-key": api_key, "Content-Type": "application/json"}, method="POST")
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
Write ONE completely original Hindi emotional micro-story for Dil Ki Diary.
Topic: {topic}

CONTENT STYLE:
Use the kind of short, instantly relatable heartbreak/emotional thought formats currently performing well on Hindi social reels: everyday digital-life details, silent heartbreak, missing someone, one-sided effort, changed relationships, late-night overthinking, and quiet self-respect. Current emotional reel content commonly uses short broken-heart/relatable formats, but DO NOT copy or paraphrase any existing viral line. Create a fresh situation and fresh wording. citeturn0search8turn0search10

CORE FORMULA — MUST FOLLOW:
SIMPLE real-life moment → RELATABLE detail → EMOTIONAL TWIST.
The viewer should think: "ये मेरे साथ भी हुआ है।"

GOOD RAW MATERIAL:
- typing a message, staring at it, then deleting it
- seeing their online status but not texting
- their birthday arriving and deciding not to wish them
- opening an old chat after months
- finding their photo while clearing phone storage
- hearing a song and remembering one exact night
- being surrounded by people but missing one person
- a friend who now replies like a stranger
- realizing you are always the one starting the conversation
- seeing their name in an old notification
- wanting to tell them something and remembering you no longer have that right
- choosing not to send one last message

WRITING RULES:
- Exactly 7 or 8 short lines total; hook is line 1.
- Prefer 3-7 words per line.
- HARD LIMIT: no line longer than about 28 Hindi characters when possible.
- Total text around 28-42 Hindi words, so it comfortably fits the notebook page.
- Natural spoken Hindi, like someone writing privately at 1 AM.
- Use one concrete detail: chat, last seen, birthday, photo, notification, call, voice note, song, etc.
- Lines 1-3: ordinary moment.
- Lines 4-6: reveal the hidden feeling.
- Last 1-2 lines: sharp emotional realization/twist.
- The final line should be the strongest and most screenshot-worthy line.
- Make the ending hurt quietly, not melodramatically.
- Do NOT make a generic quote, lecture, motivational post, or traditional shayari.
- Do NOT use recycled openings like "कुछ लोग...", "कुछ रिश्ते...", "वक्त सब सिखा देता है...", "अब किसी से उम्मीद नहीं...".
- Do NOT force rhyme.
- Do NOT use famous shayari, songs, movie dialogues, or copied/recognizable viral wording.
- No emojis, quotation marks, bullets, labels, or English words inside reel text.

Example of the FEEL only — DO NOT COPY:
आज उसका birthday था,
नाम सामने आया तो रुक गया।
wish लिखी...
फिर delete कर दी।
अजीब है ना,
जिसे कभी सबसे पहले wish करते थे,
अब उसी से बात करने का हक नहीं रहा।

Previous openings to avoid repeating:
{json.dumps(recent, ensure_ascii=False)}

Return ONLY valid JSON:
{{
  "hook": "line 1",
  "lines": ["line 2", "line 3", "line 4", "line 5", "line 6", "line 7", "line 8"],
  "caption": "1-3 natural sentences",
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
