import json
import os
import subprocess
import wave
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "assets" / "template.png"
FPS = 30
DURATION = 10
W, H = 864, 1536
TEXT_X = 205
FIRST_BASELINE = 405
LINE_GAP = 47
FONT_FAMILY = "Kalam"
FONT_SIZE = 43
INK = "#182642"


def escape_xml(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&apos;"))


def make_poster(data):
    if not TEMPLATE.exists():
        raise FileNotFoundError(f"Fixed template missing: {TEMPLATE}")

    # The master template is never regenerated or altered. Only the diary writing is overlaid.
    template = Image.open(TEMPLATE).convert("RGBA").resize((W, H), Image.Resampling.LANCZOS)
    lines = [str(data.get("hook", "")).strip()] + [str(x).strip() for x in data.get("lines", [])]
    lines = [x for x in lines if x][:5]

    svg_lines = []
    for i, line in enumerate(lines):
        y = FIRST_BASELINE + i * LINE_GAP
        # SVG/Pango performs proper Devanagari shaping; Pillow's direct text renderer was producing broken glyphs.
        svg_lines.append(
            f'<text x="{TEXT_X}" y="{y}" font-family="{FONT_FAMILY}" font-size="{FONT_SIZE}px" '
            f'font-weight="300" fill="{INK}">{escape_xml(line)}</text>'
        )

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<style>text {{ font-family: Kalam; font-size: {FONT_SIZE}px; font-weight: 300; }}</style>
{''.join(svg_lines)}
</svg>'''

    svg_path = ROOT / "output" / "poster_overlay.svg"
    overlay_path = ROOT / "output" / "poster_overlay.png"
    svg_path.write_text(svg, encoding="utf-8")
    subprocess.run(["rsvg-convert", "-o", str(overlay_path), str(svg_path)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    overlay = Image.open(overlay_path).convert("RGBA")
    poster = Image.alpha_composite(template, overlay).convert("RGB")
    poster_path = ROOT / "output" / "latest_poster.jpg"
    poster.save(poster_path, quality=95, optimize=True, progressive=True)

    print(f"Poster: {poster_path}")
    print(f"Diary lines: {lines}")
    return poster_path


def make_music_video(poster_path, out_path):
    # Original, royalty-free ambient bed synthesized locally; no external music license is needed.
    sample_rate = 44100
    n = sample_rate * DURATION
    tt = np.arange(n) / sample_rate
    notes = [(220.0, 0.040), (277.18, 0.022), (329.63, 0.015)]
    audio = sum(amp * np.sin(2 * np.pi * freq * tt) for freq, amp in notes)
    # Gentle movement so the static poster does not feel completely silent, while staying under speech/music levels.
    audio += 0.008 * np.sin(2 * np.pi * 110.0 * tt) * (0.5 + 0.5 * np.sin(2 * np.pi * tt / 4.0))
    fade = np.minimum(1.0, tt / 1.0) * np.minimum(1.0, (DURATION - tt) / 1.2)
    audio *= np.clip(fade, 0, 1)
    pcm = np.int16(np.clip(audio, -1, 1) * 32767)
    wav = out_path.with_suffix(".wav")
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())

    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(poster_path), "-i", str(wav),
        "-t", str(DURATION), "-r", str(FPS), "-vf", "scale=1080:1920:flags=lanczos,format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-c:a", "aac", "-b:a", "128k", "-shortest", str(out_path),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    wav.unlink(missing_ok=True)
    return out_path


def render(data, out_path):
    poster_path = make_poster(data)
    make_music_video(poster_path, out_path)
    for p in [ROOT / "output" / "poster_overlay.svg", ROOT / "output" / "poster_overlay.png"]:
        p.unlink(missing_ok=True)


if __name__ == "__main__":
    data = json.loads(os.environ["REEL_JSON"])
    render(data, ROOT / "output" / "latest_reel.mp4")
    print("Rendered output/latest_poster.jpg and output/latest_reel.mp4")
