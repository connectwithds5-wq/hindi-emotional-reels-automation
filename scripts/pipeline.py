import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from generate_content import generate


def main():
    data = generate()
    payload = json.dumps(data, ensure_ascii=False)
    env = os.environ.copy()
    env["REEL_JSON"] = payload
    env["BRAND_HANDLE"] = env.get("BRAND_HANDLE", "@yourhandle")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "render_reel.py")], env=env, check=True)
    (ROOT / "output" / "latest_metadata.json").write_text(payload, encoding="utf-8")
    print("TITLE/HANDLED CONTENT:")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    print("VIDEO: output/latest_reel.mp4")


if __name__ == "__main__":
    main()
