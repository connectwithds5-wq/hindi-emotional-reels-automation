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

# Fixed writing area measured against the reference template.
TEXT_X = 205
TEXT_Y = 365
TEXT_MAX_W = 585
FONT_SIZE = 38
LINE_GAP = 10
INK = (18, 27, 48, 235)


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


def wrap_words(draw, text, font, max_width):
    """Wrap Hindi into natural diary lines without changing the supplied wording."""
    words = text.split()
    lines = []
    current = []
    for word in words:
        candidate = " ".join(current + [word])
        width = draw.textbbox((0, 0), candidate, font=font)[2]
        if not current or width <= max_width:
            current.append(word)
        else:
            lines.append(current)
            current = [word]
    if current:
        lines.append(current)
    return lines


def build_layout(draw, text, font):
    """Return word positions. Each word gets tiny, deterministic human-like variation."""
    lines = wrap_words(draw, text, font, TEXT_MAX_W)
    layout = []
    y = TEXT_Y
    rng = np.random.default_rng(20260909)

    for line in lines:
        x = TEXT_X
        # Slightly irregular baseline like handwriting, while staying on notebook rules.
        base_jitter = float(rng.uniform(-1.5, 1.5))
        for word in line:
            bbox = draw.textbbox((0, 0), word, font=font)
            ww = bbox[2] - bbox[0]
            wh = bbox[3] - bbox[1]
            if x + ww > TEXT_X + TEXT_MAX_W and x > TEXT_X:
                break
            layout.append({
                "word": word,
                "x": x + float(rng.uniform(-1.0, 1.0)),
                "y": y + base_jitter + float(rng.uniform(-1.4, 1.4)),
                "angle": float(rng.uniform(-1.3, 1.3)),
                "w": ww,
                "h": wh,
            })
            space_w = draw.textlength(" ", font=font)
            x += ww + space_w + float(rng.uniform(-1.0, 2.0))
        y += font.size + LINE_GAP

    return layout, len(lines)


def draw_word(draw, item, font):
    """Render one word as a small physical ink mark, with slight rotation and soft edge."""
    word = item["word"]
    pad = 10
    tile = Image.new("RGBA", (item["w"] + pad * 2, item["h"] + pad * 2), (0, 0, 0, 0))
    td = ImageDraw.Draw(tile, "RGBA")
    td.text((pad, pad - 2), word, font=font, fill=INK)
    rotated = tile.rotate(item["angle"], resample=Image.Resampling.BICUBIC, expand=True)
    draw._image.paste(rotated, (int(item["x"] - pad), int(item["y"] - pad)), rotated)


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

    # The uploaded blank template is the permanent visual master.
    template = Image.open(TEMPLATE).convert("RGB").resize((W, H), Image.Resampling.LANCZOS)
    all_text = " ".join([str(data.get("hook", "")).strip()] + [str(x).strip() for x in data.get("lines", [])]).strip()
    total_keyframes = int(DURATION * KEYFRAME_FPS)

    # Calculate the exact word layout once. Nothing else in the template moves.
    probe = Image.new("RGB", (W, H), "white")
    probe_draw = ImageDraw.Draw(probe)
    layout, line_count = build_layout(probe_draw, all_text, font)
    word_count = len(layout)
    print(f"Fixed template: {TEMPLATE}")
    print(f"Writing layout: {word_count} words across {line_count} lines")

    # Writing starts gently and finishes before the end, leaving a natural hold.
    start_time = 0.45
    end_time = 8.25
    write_span = end_time - start_time

    for i in range(total_keyframes):
        t = i / KEYFRAME_FPS
        img = template.copy()
        draw = ImageDraw.Draw(img, "RGBA")

        if word_count:
            progress = np.clip((t - start_time) / write_span, 0.0, 1.0)
            visible = int(np.floor(progress * word_count + 1e-6))
            # Reveal one word at a time with a short soft fade, rather than typing chunks of lines.
            for idx, item in enumerate(layout):
                if idx < visible:
                    draw_word(draw, item, font)
                elif idx == visible and progress > 0:
                    frac = (progress * word_count) - visible
                    if frac > 0:
                        # Temporary layer gives the leading word a subtle ink-in effect.
                        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                        ld = ImageDraw.Draw(layer, "RGBA")
                        alpha = int(40 + 195 * min(1.0, frac * 1.35))
                        word = item["word"]
                        tile = Image.new("RGBA", (item["w"] + 20, item["h"] + 20), (0, 0, 0, 0))
                        td = ImageDraw.Draw(tile, "RGBA")
                        td.text((10, 8), word, font=font, fill=(INK[0], INK[1], INK[2], alpha))
                        rotated = tile.rotate(item["angle"], resample=Image.Resampling.BICUBIC, expand=True)
                        layer.alpha_composite(rotated, (int(item["x"] - 10), int(item["y"] - 10)))
                        img = Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")
                        draw = ImageDraw.Draw(img, "RGBA")
                    break

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
