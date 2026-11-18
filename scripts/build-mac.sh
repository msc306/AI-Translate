#!/usr/bin/env bash
# Builds the macOS app (.app inside a .dmg) on a Mac. Mirrors scripts/build-installer.ps1.
#
# Stages what the app needs into build/bundle, which tauri copies into Contents/Resources:
#   sidecar/  the Python sidecar without tests and evaluations
#   packs/    the bundled phrase packs
#   python/   a standalone Python (python-build-standalone, install_only); the sidecar core needs
#             only the standard library
# and then runs `tauri build` with src-tauri/tauri.mac.conf.json on top of the normal config.
# The app is signed ad hoc (no Apple developer account): on first start macOS asks to confirm it
# via right click > Open, or System Settings > Privacy & Security > Open Anyway.
#
# Usage: scripts/build-mac.sh [arm64|x64]   (default: the architecture of this Mac)
# Result: src-tauri/target/<triple>/release/bundle/dmg/AI Translate_<version>_<arch>.dmg

set -euo pipefail

PY_TAG="20261110"
PY_VERSION="3.12.16"
PY_SHA_ARM64="e956e60bc9465d577ef8062059aa05cd3a2665b4b8678a2ed24e432368330b8f"
PY_SHA_X64="83f2922437e6d546d0fcdb8c11f150a8e52787e8d9ea8651b1974e20908eb1bc"

arch="${1:-$(uname -m)}"
case "$arch" in
  arm64|aarch64) arch=arm64; triple=aarch64-apple-darwin; py_arch=aarch64; py_sha=$PY_SHA_ARM64 ;;
  x64|x86_64)    arch=x64;   triple=x86_64-apple-darwin;  py_arch=x86_64;  py_sha=$PY_SHA_X64 ;;
  *) echo "Unknown architecture: $arch" >&2; exit 1 ;;
esac

root="$(cd "$(dirname "$0")/.." && pwd)"
stage="$root/build/bundle"
cache="$root/build/cache"

for tool in node cargo curl shasum tar; do
  command -v "$tool" >/dev/null || { echo "Need \"$tool\" on PATH." >&2; exit 1; }
done

echo "Staging into $stage ($arch)"
rm -rf "$stage"
mkdir -p "$stage/sidecar" "$cache"
cp "$root"/sidecar/*.py "$stage/sidecar/"
cp -R "$root/packs" "$stage/packs"

archive="cpython-${PY_VERSION}+${PY_TAG}-${py_arch}-apple-darwin-install_only.tar.gz"
if [ ! -f "$cache/$archive" ]; then
  echo "Downloading $archive"
  curl --fail --location --silent --show-error --proto =https --output "$cache/$archive" \
    "https://github.com/astral-sh/python-build-standalone/releases/download/${PY_TAG}/${archive/+/%2B}"
fi
hash="$(shasum -a 256 "$cache/$archive" | cut -d' ' -f1)"
echo "$archive sha256 $hash"
[ "$hash" = "$py_sha" ] || { echo "Checksum of $archive does not match." >&2; exit 1; }

# The archive holds a top folder "python/" with bin/python3.
tar -xzf "$cache/$archive" -C "$stage"
# Trim what the sidecar never needs (keeps the app smaller).
rm -rf "$stage/python/lib/python3.12/test" "$stage/python/lib/python3.12/idlelib" \
       "$stage/python/lib/python3.12/tkinter" "$stage/python/lib/python3.12/turtledemo" \
       "$stage/python/share" "$stage/python/include"
find "$stage/python" -name "__pycache__" -type d -prune -exec rm -rf {} +

# Quick check that the staged sidecar starts with the staged Python (only when this Mac can run it)
host="$(uname -m)"; [ "$host" = "x86_64" ] && host=x64
if [ "$host" = "$arch" ]; then
  lines="$(echo '{"cmd":"shutdown"}' | "$stage/python/bin/python3" -X utf8 "$stage/sidecar/main.py" \
    --app-dir "$stage" --config "$cache/probe-config.json" | wc -l | tr -d ' ')"
  [ "$lines" -gt 0 ] || { echo "The staged sidecar did not start." >&2; exit 1; }
  echo "Staged sidecar starts: $lines line(s) of output"
fi

cd "$root"
rustup target add "$triple" >/dev/null 2>&1 || true
npx tauri build --target "$triple" --config src-tauri/tauri.mac.conf.json

ls -la "$root/src-tauri/target/$triple/release/bundle/dmg/"
for f in "$root/src-tauri/target/$triple/release/bundle/dmg/"*.dmg; do
  echo "$f  sha256 $(shasum -a 256 "$f" | cut -d' ' -f1)"
done
