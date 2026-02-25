#!/bin/bash
# Build script: bundles backend/ and frontend/ into app/ for npm publishing.
# Run from the npx-cli/ directory or invoke via `npm publish` (prepublishOnly hook).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MONO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_DIR="$SCRIPT_DIR/app"

echo "[alma-build] Bundling app into $APP_DIR ..."

rm -rf "$APP_DIR"
mkdir -p "$APP_DIR"

# Copy backend (exclude venv, __pycache__, .db files, .env)
rsync -a --exclude='venv/' --exclude='__pycache__/' --exclude='*.pyc' \
  --exclude='*.db' --exclude='*.db-shm' --exclude='*.db-wal' \
  --exclude='.env' --exclude='.smartkanban/' \
  "$MONO_ROOT/backend/" "$APP_DIR/backend/"

# Copy smartkanban.yaml (default config)
if [ -f "$MONO_ROOT/smartkanban.yaml" ]; then
  cp "$MONO_ROOT/smartkanban.yaml" "$APP_DIR/smartkanban.yaml"
  echo "[alma-build] Copied smartkanban.yaml"
fi

# Build frontend for production
echo "[alma-build] Building frontend for production..."
cd "$MONO_ROOT/frontend"
npm install --legacy-peer-deps
npm run build

# Copy only the built dist/ (no source needed for production)
mkdir -p "$APP_DIR/frontend"
cp -r "$MONO_ROOT/frontend/dist" "$APP_DIR/frontend/dist"
cp "$MONO_ROOT/frontend/package.json" "$APP_DIR/frontend/package.json"

echo "[alma-build] Done. Contents:"
du -sh "$APP_DIR/backend" "$APP_DIR/frontend"
