import json
import math
import os
import random
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
W, H = 1080, 1920
FPS = 30
DURATION = 10
KEYFRAME_FPS = 2  # 20 full-size images instead of 300 full-size images.


def font_path():
    candidates = [
        str(ROOT / "assets" / "fonts" / "Kalam-Regular.ttf"),
        "/usr/share/fonts/truetype/kalam/Kalam-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("Devanagari handwriting font not found")


def make_background(seed=0):
    rng = random.Random(seed)
    base = np.full((H, W, 3), [245, 239, 224], dtype=np.int16)
    noise = np.random.default_rng(seed).normal(0, 2.2, (H, W, 1))
    paper = np.clip(base + noise, 0, 255).astype(np.uint8)
    img = Image.fromarray(paper, "RGB")
    d = ImageDraw.Draw(img, "RGBA")
    for y in range(108, H, 82):
        wobble = rng.randint(-2, 2)
        d.line((95, y + wobble, W - 55, y + wobble), fill=(112, 137, 157, 52), width=2)
    d.line((155, 0, 155, H), fill=(190, 92, 92, 72), width=2)
    for y in range(92, H, 115):
        xoff = rng.randint(-2, 2)
        d.arc((46 + xoff, y - 30, 125 + xoff, y + 30), 198, 342, fill=(55, 55, 52, 145), width=5)
        d.line((93 + xoff, y - 26, 101 + xoff, y + 26), fill=(40, 40, 38, 70), width=2)
    for _ in range(90):
        x = rng.randint(170, W - 70)
        y = rng.randint(50, H - 50)
        r = rng.choice([1, 1, 2, 2, 3])
        d.ellipse((x, y, x + r, y + r), fill=(110, 94, 74, rng.randint(5, 16)))
    return img.filter(ImageFilter.GaussianBlur(0.15))


def wrap_lines(draw, text, font, max_width):
    words = text.split()
    lines, current = [], ""
    for word in words:
        candidate = (current + " " + word).strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_handwriting(draw, center_x, y, text, font, max_width, seed_text):
    lines = wrap_lines(draw, text, font, max_width)
    rng = random.Random(seed_text)
    yy = y
    for line in lines:
        box = draw.textbbox((0, 0), line, font=font)
        tw = box[2] - box[0]
        xx = center_x - tw / 2 + rng.uniform(-1.5, 1.5)
        yy += rng.uniform(-1.5, 1.5)
        draw.text((xx + 1.0, yy + 0.9), line, font=font, fill=(12, 24, 39, 35))
        draw.text((xx, yy), line, font=font, fill=(15, 29, 48, 238))
        yy += int(font.size * 1.16)
    return yy


def render(data, out_path):
    font_file = font_path()
    title_font = ImageFont.truetype(font_file, 62)
    body_font = ImageFont.truetype(font_file, 57)
    small_font = ImageFont.truetype(font_file, 34)
    frames_dir = ROOT / "output" / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    # Clear any frames left by an interrupted previous run.
    for p in frames_dir.glob("frame_*.jpg"):
        p.unlink()
    for p in frames_dir.glob("frame_*.png"):
        p.unlink()

    # Build the expensive notebook background only once.
    background = make_background(seed=41)

    text = [data["hook"]] + data["lines"]
    handle = os.environ.get("BRAND_HANDLE", "@yourhandle")
    total_keyframes = int(DURATION * KEYFRAME_FPS)

    print(f"Rendering {total_keyframes} keyframes at {W}x{H}, then encoding at {FPS} FPS...")
    for i in range(total_keyframes):
        t = i / KEYFRAME_FPS
        img = background.copy()
        d = ImageDraw.Draw(img, "RGBA")
        cx = W / 2 + 2.5 * math.sin(t * 0.55)
        y = 465 + 2.0 * math.sin(t * 0.38 + 1.2)

        for line in wrap_lines(d, text[0], title_font, 780):
            box = d.textbbox((0, 0), line, font=title_font)
            x = cx - (box[2] - box[0]) / 2
            d.text((x + 1, y + 1), line, font=title_font, fill=(15, 28, 43, 32))
            d.text((x, y), line, font=title_font, fill=(15, 29, 48, 242))
            y += 74

        y += 38
        for idx, original in enumerate(text[1:]):
            start = 0.8 + idx * 1.35
            progress = max(0.0, min(1.0, (t - start) / 0.65))
            if progress <= 0:
                continue
            shown = original[:max(1, int(len(original) * progress))]
            y = draw_handwriting(d, cx, y, shown, body_font, 820, f"{original}-{idx}") + 18

        d.arc((820, 335, 872, 382), 20, 310, fill=(15, 29, 48, 185), width=3)
        d.line((842, 376, 858, 393), fill=(15, 29, 48, 185), width=3)
        d.line((842, 376, 830, 392), fill=(15, 29, 48, 185), width=3)
        d.arc((250, min(H - 300, y + 35), 360, min(H - 190, y + 145)), 195, 345, fill=(15, 29, 48, 145), width=3)

        box = d.textbbox((0, 0), handle, font=small_font)
        d.text((W - 75 - (box[2] - box[0]), H - 120), handle, font=small_font, fill=(35, 45, 54, 185))
        img.save(frames_dir / f"frame_{i:03d}.jpg", quality=92, optimize=False)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    silent_video = out_path.with_name(out_path.stem + "_silent.mp4")

    subprocess.run(
        [
            "ffmpeg", "-y", "-framerate", str(KEYFRAME_FPS),
            "-i", str(frames_dir / "frame_%03d.jpg"),
            "-vf", f"fps={FPS}",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-crf", "22",
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
    import wave
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
