import json
import os
import subprocess
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "assets" / "template.png"
MUSIC = ROOT / "assets" / "music" / "background.mp3"
FPS = 30
DURATION = 10

# Render directly at the final Shorts/Reels resolution.  The previous
# pipeline first resized the template to 864x1536 and then upscaled it to
# 1080x1920 in FFmpeg, which unnecessarily softened the notebook image.
W, H = 1080, 1920
DESIGN_W, DESIGN_H = 864, 1536
SCALE = W / DESIGN_W

# --- Diary text layout calibration -----------------------------------------
# Coordinates below remain in the original 864x1536 design space and are
# scaled once, losslessly as vector text, into the final 1080x1920 frame.
TEXT_CENTER_X_TOP = 545
TEXT_CENTER_X_BOTTOM = 562
FIRST_BASELINE = 438
LINE_GAP = 48
PAGE_SLOPE_DEG = 3.0
MAX_TEXT_WIDTH = 470
FONT_FAMILY = "Kalam"
FONT_SIZE = 31
MIN_FONT_SIZE = 24
INK = "#182642"
MAX_LINES = 8


def escape_xml(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def line_center_x(index, line_count):
    if line_count <= 1:
        return TEXT_CENTER_X_TOP
    t = index / (line_count - 1)
    return TEXT_CENTER_X_TOP + (TEXT_CENTER_X_BOTTOM - TEXT_CENTER_X_TOP) * t


def font_size_for(line):
    length = len(line)
    if length <= 22:
        return FONT_SIZE
    if length <= 27:
        return 29
    if length <= 31:
        return 27
    return MIN_FONT_SIZE


def make_poster(data):
    if not TEMPLATE.exists():
        raise FileNotFoundError(f"Fixed template missing: {TEMPLATE}")

    output_dir = ROOT / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Keep the source template at the final output size.  Do not downsample
    # it to 864x1536 before compositing and then enlarge it again later.
    template = Image.open(TEMPLATE).convert("RGBA")
    if template.size != (W, H):
        template = template.resize((W, H), Image.Resampling.LANCZOS)

    raw_lines = [str(data.get("hook", "")).strip()] + [
        str(x).strip() for x in data.get("lines", [])
    ]
    lines = [x for x in raw_lines if x][:MAX_LINES]

    text_nodes = []
    line_count = len(lines)
    for i, line in enumerate(lines):
        x = line_center_x(i, line_count)
        y = FIRST_BASELINE + i * LINE_GAP
        size = font_size_for(line)
        width_hint = ""
        if len(line) > 31:
            width_hint = f' textLength="{MAX_TEXT_WIDTH}" lengthAdjust="spacingAndGlyphs"'

        text_nodes.append(
            f'<text x="{x:.2f}" y="{y:.2f}" text-anchor="middle" '
            f'font-family="{FONT_FAMILY}" font-size="{size}px" font-weight="300" '
            f'fill="{INK}"{width_hint}>{escape_xml(line)}</text>'
        )

    # Scale the entire vector text block from the calibrated design canvas to
    # the final 1080x1920 canvas.  Text therefore stays sharp instead of
    # being rasterized at 864x1536 and enlarged afterward.
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<style>text {{ font-family: Kalam; font-weight: 300; }}</style>
<g transform="scale({SCALE:.8f})">
  <g transform="rotate({PAGE_SLOPE_DEG} {TEXT_CENTER_X_TOP} {FIRST_BASELINE})">
{''.join(text_nodes)}
  </g>
</g>
</svg>'''

    svg_path = output_dir / "poster_overlay.svg"
    overlay_path = output_dir / "poster_overlay.png"
    svg_path.write_text(svg, encoding="utf-8")
    subprocess.run(
        ["rsvg-convert", "-o", str(overlay_path), str(svg_path)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    overlay = Image.open(overlay_path).convert("RGBA")
    poster = Image.alpha_composite(template, overlay).convert("RGB")
    poster_path = output_dir / "latest_poster.jpg"
    poster.save(poster_path, quality=98, optimize=True, progressive=True, subsampling=0)
    return poster_path


def make_music_video(poster_path, out_path):
    if not MUSIC.exists():
        raise FileNotFoundError(f"Music missing: {MUSIC}")

    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(poster_path), "-i", str(MUSIC),
        "-t", str(DURATION), "-r", str(FPS),
        "-vf", "scale=1080:1920:flags=lanczos,format=yuv420p",
        "-af", "afade=t=out:st=9:d=1",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
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
