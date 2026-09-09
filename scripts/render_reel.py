import json
import os
import subprocess
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "assets" / "template.png"
FPS = 30
DURATION = 10
KEYFRAME_FPS = 5
W, H = 864, 1536

# Fixed coordinates measured against the master notebook template.
TEXT_X = 205
FIRST_BASELINE = 405
FONT_SIZE = 45
LINE_GAP = 47
INK = (24, 38, 66, 224)


def font_path():
    candidates = [
        str(ROOT / "assets" / "fonts" / "Kalam-Light.ttf"),
        str(ROOT / "assets" / "fonts" / "Kalam-Regular.ttf"),
        "/usr/share/fonts/truetype/kalam/Kalam-Light.ttf",
        "/usr/share/fonts/truetype/kalam/Kalam-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    raise FileNotFoundError("Devanagari handwriting font not found")


def prepare_line(text, font, seed):
    """Create one lightly imperfect ink line without changing the notebook template."""
    rng = np.random.default_rng(seed)
    bbox = font.getbbox(text, anchor="ls")
    width = max(1, bbox[2] - bbox[0])
    height = max(1, bbox[3] - bbox[1])
    pad = 14

    layer = Image.new("RGBA", (width + pad * 2, height + pad * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    ox = pad - bbox[0]
    oy = pad - bbox[1]

    # Very soft second impression gives the strokes a slightly pressed-into-paper feel.
    draw.text((ox + 0.7, oy + 0.7), text, font=font, fill=(15, 23, 40, 38))
    draw.text((ox, oy), text, font=font, fill=INK)

    # Tiny organic variation: a barely perceptible rotation and horizontal scale.
    angle = float(rng.uniform(-0.55, 0.55))
    scale_x = float(rng.uniform(0.985, 1.015))
    layer = layer.resize((max(1, int(layer.width * scale_x)), layer.height), Image.Resampling.BICUBIC)
    layer = layer.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=(0, 0, 0, 0))

    # A faint blur blended back under the ink softens the perfectly digital edge.
    soft = layer.filter(ImageFilter.GaussianBlur(0.45))
    soft.putalpha(soft.getchannel("A").point(lambda a: int(a * 0.18)))
    result = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    result.alpha_composite(soft)
    result.alpha_composite(layer)
    return result


def draw_diary_lines(base, text_lines, font, reveal_alpha=255):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    rng = np.random.default_rng(20260909)

    y = FIRST_BASELINE
    for index, line in enumerate(text_lines):
        line = str(line).strip()
        if not line:
            continue

        ink = prepare_line(line, font, 20260909 + index)
        # Keep every line anchored to one ruled notebook line; only tiny natural drift is allowed.
        x = int(TEXT_X + rng.uniform(-1.5, 1.5))
        baseline = int(y + rng.uniform(-0.7, 0.7))
        alpha = int(reveal_alpha)
        if alpha < 255:
            ink.putalpha(ink.getchannel("A").point(lambda a: int(a * alpha / 255)))

        layer.alpha_composite(ink, (x, baseline - ink.height + 8))
        y += LINE_GAP

    return Image.alpha_composite(base.convert("RGBA"), layer).convert("RGB")


def render(data, out_path):
    if not TEMPLATE.exists():
        raise FileNotFoundError(f"Fixed template missing: {TEMPLATE}")

    font_file = font_path()
    font = ImageFont.truetype(font_file, FONT_SIZE)

    frames_dir = ROOT / "output" / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for p in frames_dir.glob("frame_*.jpg"):
        p.unlink()
    for p in frames_dir.glob("frame_*.png"):
        p.unlink()

    template = Image.open(TEMPLATE).convert("RGB").resize((W, H), Image.Resampling.LANCZOS)

    # IMPORTANT: the generated lines are already designed for the notebook ruling.
    # Never concatenate or re-wrap them. Only the written content changes from reel to reel.
    text_lines = [str(data.get("hook", "")).strip()] + [
        str(x).strip() for x in data.get("lines", [])
    ]
    text_lines = [x for x in text_lines if x][:5]

    print(f"Fixed template: {TEMPLATE}")
    print(f"Diary lines ({len(text_lines)}): {text_lines}")
    print(f"Handwriting font: {font_file}")

    total_keyframes = int(DURATION * KEYFRAME_FPS)
    for i in range(total_keyframes):
        t = i / KEYFRAME_FPS
        alpha = int(255 * np.clip((t - 0.20) / 0.45, 0.0, 1.0))
        img = draw_diary_lines(template, text_lines, font, alpha) if alpha else template.copy()
        img.save(frames_dir / f"frame_{i:03d}.jpg", quality=91, optimize=False)

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
