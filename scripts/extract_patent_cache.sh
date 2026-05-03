#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ARCHIVE="$ROOT_DIR/cache/google_patent.tar.gz"
TARGET_DIR="$ROOT_DIR/cache/google_patent"

if [ ! -f "$ARCHIVE" ]; then
    echo "Archive not found: $ARCHIVE" >&2
    exit 1
fi

mkdir -p "$ROOT_DIR/cache"
tar -xzf "$ARCHIVE" -C "$ROOT_DIR"

echo "Patent cache extracted to:"
echo "  $TARGET_DIR"

