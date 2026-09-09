# Hindi Emotional Reels Automation

Separate automation system for short, original Hindi emotional micro-story/poetry reels.

## Current flow

`Gemini → original Hindi content → notebook-style 1080×1920 reel → artifact`

The workflow is intentionally **generation-only** right now. It does not publish automatically. We will add Instagram/YouTube publishing only after the visual output is approved.

## What it creates

- 8–12 second vertical reel
- Cream notebook-paper aesthetic
- Devanagari typography
- Subtle motion
- Original ambient audio generated locally (no music API required)
- Caption, keywords and hashtags
- Content history to reduce repetition

## GitHub Actions

Workflow: `.github/workflows/daily-reel.yml`

It can be started manually from **Actions → Hindi Emotional Reel → Run workflow**, and it also has a daily schedule.

## Required secret

Add this repository secret:

- `GEMINI_API_KEY` — Gemini API key

Optional secret:

- `BRAND_HANDLE` — page handle shown on the reel, for example `@my_page`

## First test

1. Add `GEMINI_API_KEY` in **Settings → Secrets and variables → Actions**.
2. Optionally add `BRAND_HANDLE`.
3. Open **Actions**.
4. Select **Hindi Emotional Reel**.
5. Click **Run workflow**.
6. Open the completed run and download the `hindi-emotional-reel` artifact.

## Safety for the free tier

The workflow runs one short render per scheduled run, uses the GitHub-hosted runner only for generation/rendering, and keeps publishing disabled until explicitly enabled.

## Next phase

After the reel design is approved:

1. Add Instagram Reels publishing.
2. Add YouTube Shorts publishing.
3. Add a posting schedule and retry handling.
4. Add duplicate-content safeguards before publishing.
