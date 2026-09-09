import json
import math
import os
import subprocess
import textwrap
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
W, H = 1080, 1920
FPS = 30
DURATION = 10


def font_path():
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("Devanagari font not found")


def make_background():
    img = Image.new("RGB", (W, H), (247, 242, 230))
    d = ImageDraw.Draw(img)
    # Notebook ruling
    for y in range(90, H, 82):
        d.line((95, y, W - 65, y), fill=(222, 212, 194), width=2)
    # Left margin
    d.line((155, 0, 155, H), fill=(205, 170, 160), width=3)
    # Spiral rings
    for y in range(90, H, 115):
        d.arc((55, y - 26, 125, y + 26), 200, 340, fill=(92, 83, 72), width=5)
    return img


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


def render(data, out_path):
    font_file = font_path()
    title_font = ImageFont.truetype(font_file, 54)
    body_font = ImageFont.truetype(font_file, 64)
    small_font = ImageFont.truetype(font_file, 34)

    frames_dir = ROOT / "output" / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    text = [data["hook"]] + data["lines"]
    for i in range(FPS * DURATION):
        t = i / FPS
        img = make_background()
        d = ImageDraw.Draw(img)

        # Gentle Ken Burns style scale/position without expensive video rendering.
        offset = int(7 * math.sin(t * 0.8))
        x_center = W // 2 + offset
        y = 520

        # Hook
        hook_lines = wrap_lines(d, text[0], title_font, 760)
        for line in hook_lines:
            box = d.textbbox((0, 0), line, font=title_font)
            d.text((x_center - (box[2] - box[0]) / 2, y), line, font=title_font, fill=(68, 55, 46))
            y += 72
        y += 55

        # Main emotional lines
        for idx, line in enumerate(text[1:]):
            lines = wrap_lines(d, line, body_font, 800)
            alpha = min(255, max(0, int((t - 0.5 - idx * 1.1) * 255))) if t < 8 else 255
            # Draw with a tiny vertical reveal for a subtle animated feel.
            yy = y + int(max(0, 10 - alpha / 25))
            fill = (68, 55, 46)
            for sub in lines:
                box = d.textbbox((0, 0), sub, font=body_font)
                d.text((x_center - (box[2] - box[0]) / 2, yy), sub, font=body_font, fill=fill)
                yy += 86
            y = yy + 20

        # Decorative motif
        d.text((90, 140), "♥", font=small_font, fill=(137, 90, 80))
        d.text((W - 150, H - 240), "❦", font=small_font, fill=(104, 90, 75))
        handle = os.environ.get("BRAND_HANDLE", "@yourhandle")
        box = d.textbbox((0, 0), handle, font=small_font)
        d.text((W - 80 - (box[2] - box[0]), H - 110), handle, font=small_font, fill=(100, 86, 72))

        frame_path = frames_dir / f"frame_{i:04d}.png"
        img.save(frame_path, optimize=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    silent_video = out_path.with_name(out_path.stem + "_silent.mp4")
    subprocess.run([
        "ffmpeg", "-y", "-framerate", str(FPS), "-i", str(frames_dir / "frame_%04d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "22", str(silent_video)
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Generate a soft, non-copyright ambient tone and mux it into the reel.
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
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sample_rate); wf.writeframes(pcm.tobytes())

    subprocess.run([
        "ffmpeg", "-y", "-i", str(silent_video), "-i", str(wav),
        "-c:v", "copy", "-c:a", "aac", "-shortest", str(out_path)
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    for p in frames_dir.glob("*.png"):
        p.unlink()
    silent_video.unlink(missing_ok=True)
    wav.unlink(missing_ok=True)


if __name__ == "__main__":
    data = json.loads(os.environ["REEL_JSON"])
    render(data, ROOT / "output" / "latest_reel.mp4")
    print("Rendered output/latest_reel.mp4")
