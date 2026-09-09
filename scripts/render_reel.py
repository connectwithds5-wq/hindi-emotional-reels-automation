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
KEYFRAME_FPS = 5  # 50 small frames; FFmpeg creates the final 30 FPS stream.
W, H = 864, 1536


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
    raise FileNotFoundError("Devanagari handwriting font not found")


def wrap_lines(draw, text, font, max_width):
    words = text.split()
    lines = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        if not current or draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_handwritten_block(draw, text, x, y, font, max_width, progress, seed):
    """Draw a progressively revealed, slightly irregular handwritten block."""
    lines = wrap_lines(draw, text, font, max_width)
    rng = np.random.default_rng(seed)
    total_chars = sum(len(line) for line in lines) + max(0, len(lines) - 1)
    visible_chars = max(0, min(total_chars, int(total_chars * progress)))
    consumed = 0
    yy = y

    for line in lines:
        line_chars = len(line)
        if consumed >= visible_chars:
            break
        take = min(line_chars, visible_chars - consumed)
        shown = line[:take]
        box = draw.textbbox((0, 0), shown, font=font)
        tw = box[2] - box[0]
        jitter_x = float(rng.uniform(-1.5, 1.5))
        jitter_y = float(rng.uniform(-1.2, 1.2))
        # Left-aligned diary handwriting, not centered computer text.
        xx = x + jitter_x
        draw.text((xx + 0.8, yy + 0.8 + jitter_y), shown, font=font, fill=(8, 20, 42, 45))
        draw.text((xx, yy + jitter_y), shown, font=font, fill=(8, 20, 42, 238))
        yy += int(font.size * 1.18)
        consumed += line_chars + 1

    return yy


def render(data, out_path):
    if not TEMPLATE.exists():
        raise FileNotFoundError(f"Fixed template missing: {TEMPLATE}")

    font_file = font_path()
    title_font = ImageFont.truetype(font_file, 48)
    body_font = ImageFont.truetype(font_file, 39)

    frames_dir = ROOT / "output" / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for p in frames_dir.glob("frame_*.jpg"):
        p.unlink()
    for p in frames_dir.glob("frame_*.png"):
        p.unlink()

    # The uploaded reference is the permanent visual master. No new background is generated.
    template = Image.open(TEMPLATE).convert("RGB").resize((W, H), Image.Resampling.LANCZOS)
    text = [str(data["hook"]).strip()] + [str(x).strip() for x in data["lines"]]
    total_keyframes = int(DURATION * KEYFRAME_FPS)

    print(f"Using fixed template: {TEMPLATE}")
    print(f"Rendering {total_keyframes} keyframes at {W}x{H}...")

    for i in range(total_keyframes):
        t = i / KEYFRAME_FPS
        img = template.copy()
        draw = ImageDraw.Draw(img, "RGBA")

        # Writing area matches the reference page. Branding, mug, leaf, watermark, pen and footer stay untouched.
        x = 205
        y = 365
        max_width = 610

        # Hook/title appears first, then the body lines are progressively written.
        title_progress = max(0.0, min(1.0, (t - 0.20) / 1.20))
        if title_progress > 0:
            y = draw_handwritten_block(
                draw, text[0], x + 55, y, title_font, 430, title_progress, 41
            )
            y += 28

        for idx, line in enumerate(text[1:]):
            start = 1.15 + idx * 1.65
            progress = max(0.0, min(1.0, (t - start) / 1.15))
            if progress <= 0:
                continue
            y = draw_handwritten_block(
                draw, line, x, y, body_font, max_width, progress, 100 + idx
            )
            y += 16

        img.save(frames_dir / f"frame_{i:03d}.jpg", quality=90, optimize=False)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    silent_video = out_path.with_name(out_path.stem + "_silent.mp4")

    # Upscale only during the final encode. This keeps Python rendering much faster.
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

    # Keep the existing lightweight ambient audio; no external music API is needed.
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
