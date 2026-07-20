#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

VERSION="${1:-0.1.2}"
ARCHITECTURE="${2:-amd64}"
BINARY="${3:-dist/gesaula.bin}"
PACKAGE_NAME="gesaula_${VERSION}_${ARCHITECTURE}"
PACKAGE_ROOT="build/deb/${PACKAGE_NAME}"
OUTPUT="dist/${PACKAGE_NAME}.deb"

if [[ ! -x "$BINARY" ]]; then
    echo "No se encuentra un ejecutable válido en: $BINARY" >&2
    echo "Genera primero dist/gesaula.bin con Nuitka." >&2
    exit 1
fi

rm -rf "$PACKAGE_ROOT"
mkdir -p "$PACKAGE_ROOT/DEBIAN"
chmod 0755 "$PACKAGE_ROOT" "$PACKAGE_ROOT/DEBIAN"

install -Dm755 "$BINARY" "$PACKAGE_ROOT/opt/gesaula/gesaula"
install -d "$PACKAGE_ROOT/usr/bin"
ln -s /opt/gesaula/gesaula "$PACKAGE_ROOT/usr/bin/gesaula"
install -Dm644 \
    packaging/debian/gesaula.desktop \
    "$PACKAGE_ROOT/usr/share/applications/gesaula.desktop"
install -Dm644 \
    src/gesaula/icons/logo256.png \
    "$PACKAGE_ROOT/usr/share/icons/hicolor/256x256/apps/gesaula.png"
install -Dm644 README.md "$PACKAGE_ROOT/usr/share/doc/gesaula/README.md"

INSTALLED_SIZE="$(du -sk "$PACKAGE_ROOT" | cut -f1)"
sed \
    -e "s/@VERSION@/$VERSION/g" \
    -e "s/@ARCH@/$ARCHITECTURE/g" \
    -e "s/@INSTALLED_SIZE@/$INSTALLED_SIZE/g" \
    packaging/debian/control.in > "$PACKAGE_ROOT/DEBIAN/control"

mkdir -p dist
dpkg-deb --root-owner-group --build "$PACKAGE_ROOT" "$OUTPUT"

echo "Paquete creado en $OUTPUT"
