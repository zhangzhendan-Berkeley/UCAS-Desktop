"""Render our vector artwork to Windows multi-resolution icons."""
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtGui import QImage, QPainter
from PySide6.QtCore import Qt
from PIL import Image

root = Path(__file__).resolve().parents[1]
app = QApplication([])
canvas = QImage(256, 256, QImage.Format_ARGB32)
canvas.fill(Qt.transparent)
painter = QPainter(canvas)
QSvgRenderer(str(root / 'assets/app.svg')).render(painter)
painter.end()
canvas.save(str(root / 'assets/app.png'))
Image.open(root / 'assets/app.png').save(
    root / 'assets/app.ico', sizes=[(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)])
