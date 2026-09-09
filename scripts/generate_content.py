import json
import os
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
HISTORY_PATH = ROOT / "data" / "content_history.json"
STRATEGY_PATH = ROOT / "data" / "strategy.json"


def load_history():
    if not HISTORY_PATH.exists():
        return []
    return json.loads(HISTORY_PATH.read_text(encoding="utf-8")).get("items", [])


def load_strategy():
    if not STRATEGY_PATH.exists():
        return {}
    try:
        return json.loads(STRATEGY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_history(items):
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps({"items": items[-100:]}, ensure_ascii=False, indent=2), encoding="utf-8")


def call_gemini_rest(api_key, model, prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.95, "maxOutputTokens": 900},
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
    strategy = load_strategy()
    recent = [x.get("hook", "") for x in history[-30:]]
    next_video = strategy.get("next_video", {})
    topic = next_video.get("topic") or CONFIG["topics"][len(history) % len(CONFIG["topics"])]
    strategy_context = {
        "confidence": strategy.get("confidence", ""),
        "experiment": strategy.get("experiment", ""),
        "next_video": next_video,
    }
    strategy_context_text = json.dumps(strategy_context, ensure_ascii=False, indent=2) if next_video else "No AI strategy is available yet; choose a fresh controlled baseline."

    prompt = f"""
Write ONE completely original Hindi emotional micro-story for Dil Ki Diary.
Topic: {topic}

AI GROWTH STRATEGY — USE THIS AS THE DECISION INPUT:
{strategy_context_text}
The strategy is a recommendation, not permission to copy wording. Preserve originality while following its topic, emotion, hook direction and experiment when appropriate. The experiment is important: make the creative choice actually test the stated hypothesis while keeping the story natural.

CONTENT STYLE:
Use short, instantly relatable emotional-reel storytelling: everyday digital-life details, silent heartbreak, missing someone, one-sided effort, changed relationships, late-night overthinking, and quiet self-respect. Use fresh wording only; never copy or closely paraphrase existing viral content.

CORE FORMULA — MUST FOLLOW:
SIMPLE real-life moment → RELATABLE detail → EMOTIONAL TWIST.
The viewer should think: "ये मेरे साथ भी हुआ है।"

WRITING RULES:
- Exactly 7 or 8 short lines total; hook is line 1.
- Prefer 3-7 words per line.
- HARD LIMIT: no line longer than about 28 Hindi characters when possible.
- Total text around 28-42 Hindi words, so it comfortably fits the notebook page.
- Natural spoken Hindi, like someone writing privately at 1 AM.
- Use one concrete detail: chat, last seen, birthday, photo, notification, call, voice note, song, tea cup, empty chair, room, etc., chosen to match the strategy.
- Lines 1-3: ordinary moment.
- Lines 4-6: reveal the hidden feeling.
- Last 1-2 lines: sharp emotional realization/twist.
- The final line should be the strongest and most screenshot-worthy line.
- Make the ending hurt quietly, not melodramatically.
- Do NOT make a generic quote, lecture, motivational post, or traditional shayari.
- Do NOT use recycled openings like "कुछ लोग...", "कुछ रिश्ते...", "वक्त सब सिखा देता है...".
- Do NOT force rhyme.
- Do NOT use famous shayari, songs, movie dialogues, or copied/recognizable viral wording.
- No emojis, quotation marks, bullets, labels, or English words inside reel text.

YOUTUBE SHORTS SEO METADATA:
- Create a searchable but natural title using the hook and the main emotional topic. Keep it concise; target roughly 45-65 characters when possible. Do not keyword-stuff.
- Write a YouTube description of 2-4 natural sentences. Put the primary topic phrase naturally in the first sentence, explain the emotional situation, and end with a simple engagement question only when it feels natural.
- Create 10-15 YouTube search keywords/phrases. Mix Hindi and Roman-Hindi variations relevant to this exact story: topic, emotion, situation, and audience intent. Do not add unrelated high-volume terms.
- Create 6-10 highly relevant hashtags. Prefer specific topic/story hashtags plus 1-2 broad discovery hashtags. Do not repeat the same word excessively.
- Also provide an Instagram-style caption separately, but keep it natural and story-specific.
- SEO must describe the actual video. Never use misleading clickbait, unrelated trending keywords, celebrity names, or copied viral phrases.

Example of the FEEL only — DO NOT COPY:
आज उसका birthday था,
नाम सामने आया तो रुक गया।
फिर message लिखकर मिटा दिया।
अजीब है ना,
जिसे कभी सबसे पहले wish करते थे,
अब उसी से बात करने का हक नहीं रहा।

Previous openings to avoid repeating:
{json.dumps(recent, ensure_ascii=False)}

Return ONLY valid JSON:
{{
  "hook": "line 1",
  "lines": ["line 2", "line 3", "line 4", "line 5", "line 6", "line 7", "line 8"],
  "youtube_title": "SEO-friendly YouTube Shorts title",
  "youtube_description": "2-4 natural SEO-aware sentences",
  "youtube_keywords": ["10-15 relevant search phrases"],
  "youtube_hashtags": ["6-10 relevant hashtags without #"],
  "caption": "Instagram-style natural caption",
  "keywords": ["8-12 relevant search keywords"],
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
    data["strategy_used"] = next_video
    data["model_used"] = used_model
    data["hook"] = str(data.get("hook", "")).strip()
    data["lines"] = [str(x).strip() for x in data.get("lines", [])][:7]
    data["youtube_title"] = str(data.get("youtube_title", data["hook"])).strip()
    data["youtube_description"] = str(data.get("youtube_description", data.get("caption", ""))).strip()
    data["youtube_keywords"] = [str(x).strip() for x in data.get("youtube_keywords", []) if str(x).strip()]
    data["youtube_hashtags"] = [str(x).strip().lstrip("#") for x in data.get("youtube_hashtags", []) if str(x).strip()]
    data["caption"] = str(data.get("caption", "")).strip()
    data["keywords"] = [str(x).strip() for x in data.get("keywords", [])]
    data["hashtags"] = [str(x).strip().lstrip("#") for x in data.get("hashtags", [])]
    history.append(data)
    save_history(history)
    return data


if __name__ == "__main__":
    print(json.dumps(generate(), ensure_ascii=False, indent=2))
