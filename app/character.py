"""An original, code-drawn chibi used when no PNG is available."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap, QPolygonF


def create_placeholder() -> QPixmap:
    # Draw at twice the display resolution to keep curves smooth on HiDPI screens.
    pixmap = QPixmap(400, 480)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(2, 2)

    outline = QColor("#544168")

    def ellipse(x: float, y: float, w: float, h: float, color: str) -> None:
        painter.setPen(QPen(outline, 2.5))
        painter.setBrush(QColor(color))
        painter.drawEllipse(QRectF(x, y, w, h))

    def shape(points: list[tuple[float, float]], color: str) -> None:
        painter.setPen(
            QPen(outline, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                 Qt.PenJoinStyle.RoundJoin)
        )
        painter.setBrush(QColor(color))
        painter.drawPolygon(QPolygonF([QPointF(x, y) for x, y in points]))

    # Oversized hair, short limbs, and a tiny dress give a simple chibi silhouette.
    ellipse(29, 49, 48, 122, "#b39bdf")
    ellipse(123, 49, 48, 122, "#b39bdf")
    ellipse(73, 191, 22, 34, "#ffe4d6")
    ellipse(105, 191, 22, 34, "#ffe4d6")
    ellipse(67, 215, 30, 15, "#796397")
    ellipse(103, 215, 30, 15, "#796397")
    ellipse(50, 149, 24, 40, "#ffe4d6")
    ellipse(126, 149, 24, 40, "#ffe4d6")
    shape([(76, 143), (124, 143), (139, 202), (61, 202)], "#b9e5df")
    shape([(77, 144), (100, 164), (123, 144)], "#fff8f4")
    shape([(100, 164), (86, 157), (86, 173)], "#ee9ebb")
    shape([(100, 164), (114, 157), (114, 173)], "#ee9ebb")

    ellipse(36, 22, 128, 128, "#b39bdf")
    ellipse(43, 48, 114, 98, "#ffe4d6")

    fringe = QPainterPath(QPointF(39, 80))
    fringe.cubicTo(29, 7, 169, 7, 161, 82)
    fringe.quadTo(140, 75, 127, 52)
    fringe.quadTo(125, 78, 106, 86)
    fringe.lineTo(107, 59)
    fringe.quadTo(82, 87, 65, 85)
    fringe.lineTo(73, 61)
    fringe.quadTo(53, 80, 39, 80)
    painter.setBrush(QColor("#b39bdf"))
    painter.setPen(QPen(outline, 2.5))
    painter.drawPath(fringe)

    ellipse(65, 91, 17, 27, "#655280")
    ellipse(118, 91, 17, 27, "#655280")
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#ffffff"))
    painter.drawEllipse(QRectF(68, 94, 6, 9))
    painter.drawEllipse(QRectF(121, 94, 6, 9))
    painter.setBrush(QColor("#f5b0bc"))
    painter.drawEllipse(QRectF(53, 115, 22, 10))
    painter.drawEllipse(QRectF(125, 115, 22, 10))
    painter.setPen(QPen(outline, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    smile = QPainterPath(QPointF(91, 122))
    smile.quadTo(100, 132, 109, 122)
    painter.drawPath(smile)

    # A little star hair clip, with no external fonts or assets required.
    shape(
        [(145, 42), (149, 50), (158, 52), (151, 58), (152, 67),
         (145, 63), (137, 67), (139, 58), (132, 52), (141, 50)],
        "#ffe6a0",
    )
    painter.end()
    return pixmap
