#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$ROOT/scripts/readme-cover.html"
OUTPUT="$ROOT/.github/assets/sindie-cover.png"
NEGATIVE_CONTROL="$ROOT/.runs/fixtures/negative-control/night-market-poster/artifact.png"

if [[ ! -f "$NEGATIVE_CONTROL" ]]; then
  printf 'Missing local negative-control fixture: %s\n' "$NEGATIVE_CONTROL" >&2
  printf 'Generate or restore that fixture before rendering this cover.\n' >&2
  exit 1
fi

if [[ -n "${CHROME_BIN:-}" ]]; then
  CHROME="$CHROME_BIN"
elif [[ -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]]; then
  CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
elif command -v google-chrome >/dev/null 2>&1; then
  CHROME="$(command -v google-chrome)"
elif command -v chromium >/dev/null 2>&1; then
  CHROME="$(command -v chromium)"
elif command -v chromium-browser >/dev/null 2>&1; then
  CHROME="$(command -v chromium-browser)"
else
  printf 'Chrome or Chromium is required. Set CHROME_BIN to its executable.\n' >&2
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT")"

"$CHROME" \
  --headless=new \
  --disable-gpu \
  --hide-scrollbars \
  --allow-file-access-from-files \
  --force-device-scale-factor=1 \
  --run-all-compositor-stages-before-draw \
  --virtual-time-budget=1000 \
  --window-size=2880,1120 \
  --screenshot="$OUTPUT" \
  "file://$SOURCE" >/dev/null 2>&1

printf '%s\n' "$OUTPUT"
