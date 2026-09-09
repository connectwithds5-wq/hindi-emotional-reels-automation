import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
ANALYTICS = ROOT / "data" / "analytics_history.json"
HISTORY = ROOT / "data" / "content_history.json"
OUTPUT = ROOT / "data" / "strategy.json"


def read_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def normalize_title(value):
    return " ".join(str(value or "").lower().replace("#shorts", "").split())


def latest_video_metrics(records):
    latest = {}
    for row in records:
        vid = row.get("video_id")
        if not vid:
            continue
        old = latest.get(vid)
        if old is None or row.get("collected_at", "") >= old.get("collected_at", ""):
            latest[vid] = row
    return list(latest.values())


def build_dataset():
    analytics = latest_video_metrics(read_json(ANALYTICS, []))
    history = read_json(HISTORY, {}).get("items", [])
    by_title = {normalize_title(x.get("youtube_title") or x.get("hook")): x for x in history}
    rows = []
    for a in analytics:
        content = by_title.get(normalize_title(a.get("title")), {})
        rows.append({
            "video_id": a.get("video_id", ""),
            "title": a.get("title", ""),
            "views": int(a.get("views", 0)),
            "likes": int(a.get("likes", 0)),
            "comments": int(a.get("comments", 0)),
            "published_at": a.get("published_at", ""),
            "topic": content.get("topic", "unknown"),
            "hook": content.get("hook", ""),
            "caption": content.get("caption", ""),
        })
    return rows


def call_gemini(api_key, model, dataset, topics):
    prompt = f"""You are the growth strategist for a Hindi emotional Shorts channel called Dil Ki Diary.
Analyze the supplied historical performance and recommend the NEXT video. Do not chase one lucky low-sample result. Prefer repeatable patterns, but reserve a small experiment budget.

CHANNEL TOPICS: {json.dumps(topics, ensure_ascii=False)}
PERFORMANCE DATA: {json.dumps(dataset[-30:], ensure_ascii=False)}

Rules:
- Identify winning and weak patterns from the actual data.
- If data is too small, explicitly say confidence is low and use a controlled exploration recommendation.
- Recommend exactly one next video concept.
- The concept must follow: simple real-life moment -> relatable detail -> emotional twist.
- Avoid generic quotes, copied viral wording, and repetitive openings.
- Recommend a posting window using available evidence; otherwise choose a sensible test window.
- Keep the recommendation actionable for the content generator.
- Return ONLY valid JSON.

Schema:
{{
  "confidence": "0-100%",
  "data_points": 0,
  "overall_summary": "short explanation",
  "winning_patterns": [{{"pattern":"...","evidence":"...","action":"..."}}],
  "weak_patterns": [{{"pattern":"...","evidence":"...","action":"..."}}],
  "next_video": {{
    "topic":"...","emotion":"...","hook_style":"...","story_structure":"simple -> relatable -> twist",
    "concept":"...","opening_direction":"...","twist_direction":"...","duration_seconds":10,
    "posting_window":"...","reason":"..."
  }},
  "experiment": "what is being tested",
  "updated_at": "{datetime.now(timezone.utc).isoformat()}"
}}
"""
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0.35, "maxOutputTokens": 1400}}
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini HTTP {exc.code}: {detail[:500]}") from exc
    except Exception as exc:
        raise RuntimeError(f"Strategy Gemini failed: {exc}") from exc


def fallback(dataset, topics):
    if dataset:
        ranked = sorted(dataset, key=lambda x: (x["views"], x["likes"], x["comments"]), reverse=True)
        best = ranked[0]
        summary = f"Current leader: {best['title']} with {best['views']} views; sample size is still small, so this is directional."
        topic = best.get("topic") if best.get("topic") not in (None, "", "unknown") else topics[0]
    else:
        ranked, best = [], {}
        summary = "No usable analytics yet; start with a controlled baseline and learn from the first results."
        topic = topics[0]
    return {
        "confidence": "25%" if len(dataset) < 5 else "45%",
        "data_points": len(dataset),
        "overall_summary": summary,
        "winning_patterns": ([{"pattern": "Highest observed views", "evidence": f"{best.get('views', 0)} views on current leader", "action": "Test a related emotional situation without copying the wording."}] if best else []),
        "weak_patterns": [],
        "next_video": {
            "topic": topic,
            "emotion": "regret",
            "hook_style": "curiosity",
            "story_structure": "simple -> relatable -> twist",
            "concept": "A familiar chat or notification reveals that the relationship has quietly changed.",
            "opening_direction": "Start with one concrete digital-life detail.",
            "twist_direction": "Reveal the emotional meaning in the final line.",
            "duration_seconds": 10,
            "posting_window": "7:00 PM IST test",
            "reason": "Controlled baseline while more performance data accumulates."
        },
        "experiment": "Test a fresh hook around a concrete digital-life moment.",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def main():
    dataset = build_dataset()
    topics = CONFIG.get("topics", [])
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    models = [CONFIG.get("model"), CONFIG.get("lite_model"), CONFIG.get("legacy_lite_model")]
    models = [m for i, m in enumerate(models) if m and m not in models[:i]]
    strategy = None
    used_model = None
    if api_key:
        for model in models:
            try:
                print(f"Trying strategy model: {model}")
                strategy = call_gemini(api_key, model, dataset, topics)
                used_model = model
                break
            except Exception as exc:
                print(exc)
    if not strategy:
        strategy = fallback(dataset, topics)
        used_model = "deterministic-fallback"
    strategy["model_used"] = used_model
    strategy["generated_at"] = datetime.now(timezone.utc).isoformat()
    strategy["data_points"] = len(dataset)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(strategy, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(strategy, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
