"""Render the vector brand mark into a standards-compliant macOS .icns file."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QRectF, QSize
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


SIZES = {
    "icon_16x16.png": 16,
    "icon_16x16@2x.png": 32,
    "icon_32x32.png": 32,
    "icon_32x32@2x.png": 64,
    "icon_128x128.png": 128,
    "icon_128x128@2x.png": 256,
    "icon_256x256.png": 256,
    "icon_256x256@2x.png": 512,
    "icon_512x512.png": 512,
    "icon_512x512@2x.png": 1024,
}


def main() -> int:
    if sys.platform != "darwin":
        raise SystemExit("This icon builder must run on macOS")
    root = Path(__file__).resolve().parents[1]
    source = root / "app/resources/branding/lagshift-route-prism.svg"
    iconset = root / "build/macos/LAGSHIFT.iconset"
    output = root / "build/macos/LAGSHIFT.icns"
    iconset.mkdir(parents=True, exist_ok=True)
    app = QGuiApplication.instance() or QGuiApplication([])
    renderer = QSvgRenderer(str(source))
    if not renderer.isValid():
        raise RuntimeError("Brand SVG could not be rendered")
    for filename, pixels in SIZES.items():
        image = QImage(QSize(pixels, pixels), QImage.Format_ARGB32_Premultiplied)
        image.fill(0)
        painter = QPainter(image)
        renderer.render(painter, QRectF(0, 0, pixels, pixels))
        painter.end()
        if not image.save(str(iconset / filename), "PNG"):
            raise RuntimeError(f"Could not write {filename}")
    subprocess.run(
        ["/usr/bin/iconutil", "-c", "icns", str(iconset), "-o", str(output)],
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
