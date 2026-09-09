import json
import os
import subprocess
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "assets" / "template.png"
FPS = 30
DURATION = 10
KEYFRAME_FPS = 5
W, H = 864, 1536

# Measured against the fixed notebook template.
TEXT_X = 205
FIRST_BASELINE = 405
TEXT_MAX_W = 600
FONT_SIZE = 42
LINE_GAP = 47
INK = (24, 38, 66, 238)


def font_path():
    candidates = [
        str(ROOT / "assets" / "fonts" / "Kalam-Regular.ttf"),
        "/usr/share/fonts/truetype/kalam/Kalam-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    raise FileNotFoundError("Devanagari font not found")


def wrap_words(draw, text, font, max_width):
    words = text.split()
    lines = []
    current = []
    for word in words:
        candidate = " ".join(current + [word])
        width = draw.textbbox((0, 0), candidate, font=font)[2]
        if not current or width <= max_width:
            current.append(word)
        else:
            lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines


def draw_diary_passage(base, text_lines, font, reveal_alpha=255):
    """Draw polished diary text with baselines locked to notebook rulings."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    rng = np.random.default_rng(20260909)

    y = FIRST_BASELINE
    for line in text_lines:
        # Tiny natural variation without losing alignment with the ruled paper.
        x = TEXT_X + float(rng.uniform(-1.0, 1.0))
        baseline = y + float(rng.uniform(-0.6, 0.6))

        # Soft ink edge, then the main blue-black stroke.
        draw.text(
            (x + 0.8, baseline + 0.8),
            line,
            font=font,
            anchor="ls",
            fill=(15, 23, 40, int(45 * reveal_alpha / 255)),
        )
        draw.text(
            (x, baseline),
            line,
            font=font,
            anchor="ls",
            fill=(INK[0], INK[1], INK[2], int(INK[3] * reveal_alpha / 255)),
        )
        y += LINE_GAP

    return Image.alpha_composite(base.convert("RGBA"), layer).convert("RGB")


def render(data, out_path):
    if not TEMPLATE.exists():
        raise FileNotFoundError(f"Fixed template missing: {TEMPLATE}")

    font_file = font_path()
    # Kalam remains the handwriting face; the larger size makes it look like actual diary writing
    # rather than small UI text.
    font = ImageFont.truetype(font_file, FONT_SIZE)

    frames_dir = ROOT / "output" / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for p in frames_dir.glob("frame_*.jpg"):
        p.unlink()
    for p in frames_dir.glob("frame_*.png"):
        p.unlink()

    template = Image.open(TEMPLATE).convert("RGB").resize((W, H), Image.Resampling.LANCZOS)

    # Hook is no longer rendered as a separate title. It becomes the opening sentence of one diary passage.
    all_text = " ".join(
        [str(data.get("hook", "")).strip()]
        + [str(x).strip() for x in data.get("lines", [])]
    ).strip()

    probe = ImageDraw.Draw(Image.new("RGB", (W, H), "white"))
    text_lines = wrap_words(probe, all_text, font, TEXT_MAX_W)
    text_lines = text_lines[:5]

    print(f"Fixed template: {TEMPLATE}")
    print(f"Diary passage ({len(text_lines)} ruled lines): {text_lines}")

    total_keyframes = int(DURATION * KEYFRAME_FPS)

    for i in range(total_keyframes):
        t = i / KEYFRAME_FPS

        # No typewriter effect. The complete passage gently fades in in the first ~0.7 sec,
        # then remains completely static for a clean diary-photo feel.
        alpha = int(255 * np.clip((t - 0.25) / 0.55, 0.0, 1.0))
        if alpha:
            img = draw_diary_passage(template, text_lines, font, alpha)
        else:
            img = template.copy()

        img.save(frames_dir / f"frame_{i:03d}.jpg", quality=90, optimize=False)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    silent_video = out_path.with_name(out_path.stem + "_silent.mp4")

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-framerate", str(KEYFRAME_FPS),
            "-i", str(frames_dir / "frame_%03d.jpg"),
            "-vf", f"fps={FPS},scale=1080:1920:flags=lanczos",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-crf", "21",
            str(silent_video),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    sample_rate = 44100
    n = sample_rate * DURATION
    tt = np.arange(n) / sample_rate
    audio = 0.035 * np.sin(2 * np.pi * 220 * tt) + 0.018 * np.sin(2 * np.pi * 277.18 * tt)
    fade = np.minimum(1, tt / 1.2) * np.minimum(1, (DURATION - tt) / 1.5)
    audio *= np.clip(fade, 0, 1)
    pcm = np.int16(np.clip(audio, -1, 1) * 32767)
    wav = out_path.with_suffix(".wav")
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())

    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(silent_video), "-i", str(wav),
            "-c:v", "copy", "-c:a", "aac", "-shortest", str(out_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    for p in frames_dir.glob("frame_*.jpg"):
        p.unlink()
    silent_video.unlink(missing_ok=True)
    wav.unlink(missing_ok=True)


if __name__ == "__main__":
    data = json.loads(os.environ["REEL_JSON"])
    render(data, ROOT / "output" / "latest_reel.mp4")
    print("Rendered output/latest_reel.mp4")
