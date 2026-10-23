"""A small, non-activating speech bubble owned by the companion window."""

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget


class SpeechBubble(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.WindowDoesNotAcceptFocus
                         | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFont(QFont("Segoe UI", 10))
        self._text = ""
        self._below = False
        self._tail_x = 30.0
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)

    def show_message(self, text: str, anchor: QRect, area: QRect, duration_ms: int) -> None:
        self._text = text
        width = max(1, min(220, area.width() - 28))
        bounds = self.fontMetrics().boundingRect(
            QRect(0, 0, width, 1000), Qt.TextFlag.TextWordWrap, text,
        )
        self.resize(min(area.width(), max(90, bounds.width() + 28)),
                    min(area.height(), bounds.height() + 36))
        self.place_near(anchor, area)
        self.update()
        self.show()
        self._timer.start(duration_ms)

    def place_near(self, anchor: QRect, area: QRect) -> None:
        previous_tail = (self._below, self._tail_x)
        x = anchor.center().x() - self.width() // 2
        above = anchor.top() - self.height() - 8
        self._below = above < area.top()
        y = anchor.bottom() + 9 if self._below else above
        x = max(area.left(), min(x, area.right() + 1 - self.width()))
        y = max(area.top(), min(y, area.bottom() + 1 - self.height()))
        self._tail_x = max(18, min(anchor.center().x() - x, self.width() - 18))
        self.move(x, y)
        if previous_tail != (self._below, self._tail_x):
            self.update()

    def dismiss(self) -> None:
        self._timer.stop()
        self.hide()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#d7a7c7"), 1.2))
        painter.setBrush(QColor("#fff4fb"))
        top = 9 if self._below else 1
        body = QRectF(1, top, self.width() - 2, self.height() - 10)
        painter.drawRoundedRect(body, 14, 14)
        base = body.top() + 1 if self._below else body.bottom() - 1
        tip = 1 if self._below else self.height() - 1
        painter.drawPolygon(QPolygonF([
            QPointF(self._tail_x - 6, base), QPointF(self._tail_x, tip),
            QPointF(self._tail_x + 6, base),
        ]))
        painter.setPen(QColor("#65475f"))
        painter.drawText(body.adjusted(12, 8, -12, -8),
                         Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self._text)

    def closeEvent(self, event) -> None:
        self._timer.stop()
        super().closeEvent(event)
