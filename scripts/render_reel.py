import json
import os
import subprocess
import wave
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "assets" / "template.png"
MUSIC = ROOT / "assets" / "music" / "background.mp3"
FPS = 30
DURATION = 10
W, H = 864, 1536

# Small, centered diary writing aligned to the photographed notebook ruling.
TEXT_CENTER_X = 545
FIRST_BASELINE = 438
LINE_GAP = 48
PAGE_SLOPE_DEG = 3.0
FONT_FAMILY = "Kalam"
FONT_SIZE = 31
INK = "#182642"


def escape_xml(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&apos;"))


def make_poster(data):
    if not TEMPLATE.exists():
        raise FileNotFoundError(f"Fixed template missing: {TEMPLATE}")
    output_dir = ROOT / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    template = Image.open(TEMPLATE).convert("RGBA").resize((W, H), Image.Resampling.LANCZOS)

    lines = [str(data.get("hook", "")).strip()] + [str(x).strip() for x in data.get("lines", [])]
    lines = [x for x in lines if x][:8]

    svg_lines = []
    # Keep the text comfortably inside the writing area. Longer lines are reduced slightly.
    for i, line in enumerate(lines):
        y = FIRST_BASELINE + i * LINE_GAP
        size = 31 if len(line) <= 27 else 28
        svg_lines.append(
            f'<text x="{TEXT_CENTER_X}" y="{y}" text-anchor="middle" '
            f'transform="rotate({PAGE_SLOPE_DEG} {TEXT_CENTER_X} {y})" '
            f'font-family="{FONT_FAMILY}" font-size="{size}px" font-weight="300" '
            f'fill="{INK}">{escape_xml(line)}</text>'
        )

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<style>text {{ font-family: Kalam; font-weight: 300; }}</style>
{''.join(svg_lines)}
</svg>'''
    svg_path = output_dir / "poster_overlay.svg"
    overlay_path = output_dir / "poster_overlay.png"
    svg_path.write_text(svg, encoding="utf-8")
    subprocess.run(["rsvg-convert", "-o", str(overlay_path), str(svg_path)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    overlay = Image.open(overlay_path).convert("RGBA")
    poster = Image.alpha_composite(template, overlay).convert("RGB")
    poster_path = output_dir / "latest_poster.jpg"
    poster.save(poster_path, quality=95, optimize=True, progressive=True)
    return poster_path


def make_music_video(poster_path, out_path):
    if not MUSIC.exists():
        raise FileNotFoundError(f"Music missing: {MUSIC}")
    # The uploaded track is the source of truth: final video is exactly 10 seconds.
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(poster_path), "-i", str(MUSIC),
        "-t", str(DURATION), "-r", str(FPS),
        "-vf", "scale=1080:1920:flags=lanczos,format=yuv420p",
        "-af", "afade=t=out:st=9:d=1",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-c:a", "aac", "-b:a", "192k", "-shortest", str(out_path),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out_path


def render(data, out_path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    poster_path = make_poster(data)
    make_music_video(poster_path, out_path)
    for p in [ROOT / "output" / "poster_overlay.svg", ROOT / "output" / "poster_overlay.png"]:
        p.unlink(missing_ok=True)


if __name__ == "__main__":
    data = json.loads(os.environ["REEL_JSON"])
    render(data, ROOT / "output" / "latest_reel.mp4")
    print("Rendered output/latest_poster.jpg and output/latest_reel.mp4")
