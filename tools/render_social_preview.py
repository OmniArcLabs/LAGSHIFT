from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, QSize
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "assets" / "lagshift-social-preview.svg"
OUTPUT = ROOT / "docs" / "assets" / "lagshift-social-preview.jpg"


def main() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    renderer = QSvgRenderer(QByteArray(SOURCE.read_bytes()))
    if not renderer.isValid():
        raise RuntimeError(f"Invalid SVG: {SOURCE}")

    size = QSize(1280, 640)
    image = QImage(size, QImage.Format.Format_RGB32)
    image.fill(0xFF04090D)
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, size.width(), size.height()))
    painter.end()

    if not image.save(str(OUTPUT), "JPG", 92):
        raise RuntimeError(f"Could not write {OUTPUT}")
    del renderer, image
    app.quit()


if __name__ == "__main__":
    main()
