"""
ui/widgets.py — 재사용 UI 부품들
================================================
화면을 구성하는 작은 조각들을 모아둔 곳입니다.
  · MenuCard       : 메뉴 한 개를 보여주는 큰 카드 버튼
  · CartItemRow    : 장바구니의 한 줄(수량 +/- 포함)
  · GestureCursor  : 손동작으로 움직이는 동그란 커서
  · Toast          : 잠깐 떴다 사라지는 알림 말풍선
"""
from __future__ import annotations

from PyQt6.QtCore import (Qt, QTimer, pyqtSignal, QPropertyAnimation, QPoint,
                          QRect, QSize)
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLayout, QPushButton,
                             QSizePolicy, QVBoxLayout, QWidget,
                             QGraphicsOpacityEffect)

from core.menu_data import MenuItem
from core.order import CartLine


class FlowLayout(QLayout):
    """가로 폭이 모자라면 자동으로 다음 줄로 넘기는(wrap) 레이아웃.

    영어·중국어처럼 글자가 길어져 한 줄에 다 들어가지 않아도 항목이
    잘리지 않고 아래 줄로 흘러내려 모두 화면에 보이도록 합니다.
    alignment="center" 면 각 줄을 가운데로 정렬합니다.
    """

    def __init__(self, parent=None, margin=0, spacing=8, alignment="left"):
        super().__init__(parent)
        self._items: list = []
        self._alignment = alignment
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        # 권장 크기 = '한 줄로 모두 펼쳤을 때'의 자연 크기.
        # (폭은 전체 합, 높이는 한 줄)  ← 이렇게 해야 heightForWidth 가
        # 좁은 폭에서 항목을 세로로 쌓아 최소 높이를 부풀리는 일이 없다.
        w, h = 0, 0
        for i, item in enumerate(self._items):
            hint = item.sizeHint()
            w += hint.width() + (self.spacing() if i else 0)
            h = max(h, hint.height())
        m = self.contentsMargins()
        return QSize(w + m.left() + m.right(), h + m.top() + m.bottom())

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect, test_only):
        m = self.contentsMargins()
        x0 = rect.x() + m.left()
        y0 = rect.y() + m.top()
        max_w = rect.width() - m.left() - m.right()
        spacing = self.spacing()

        # 1) 항목을 줄 단위로 묶는다
        rows: list = []
        cur, cur_w, cur_h = [], 0, 0
        for item in self._items:
            hint = item.sizeHint()
            w, h = hint.width(), hint.height()
            add_w = w if not cur else spacing + w
            if cur and cur_w + add_w > max_w:
                rows.append((cur, cur_w, cur_h))
                cur, cur_w, cur_h = [], 0, 0
                add_w = w
            cur.append((item, w, h))
            cur_w += add_w
            cur_h = max(cur_h, h)
        if cur:
            rows.append((cur, cur_w, cur_h))

        # 2) 각 줄을 배치(필요하면 가운데 정렬)
        y = y0
        for items, row_w, row_h in rows:
            x = x0 + max(0, (max_w - row_w) // 2) if self._alignment == "center" else x0
            for item, w, h in items:
                if not test_only:
                    item.setGeometry(QRect(QPoint(x, y + (row_h - h) // 2),
                                           QSize(w, h)))
                x += w + spacing
            y += row_h + spacing
        return (y - spacing) + m.bottom() if rows else (m.top() + m.bottom())


class MenuCard(QPushButton):
    """메뉴 1개를 큰 그림+이름+가격으로 보여주는 카드 버튼."""

    def __init__(self, item: MenuItem, lang: str, won: str, parent=None):
        super().__init__(parent)
        self.item = item
        self.setObjectName("MenuCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(190, 210)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 14, 10, 14)
        lay.setSpacing(6)

        emoji = QLabel(item.emoji)
        emoji.setObjectName("Emoji")
        emoji.setAlignment(Qt.AlignmentFlag.AlignCenter)

        name = QLabel(item.name(lang))
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setWordWrap(True)
        name.setStyleSheet("font-weight:700;")

        price = QLabel(f"{item.price:,}{won}")
        price.setObjectName("Price")
        price.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lay.addWidget(emoji)
        lay.addWidget(name)
        lay.addWidget(price)
        if item.is_best:
            badge = QLabel("BEST")
            badge.setObjectName("Badge")
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setMaximumWidth(80)
            wrap = QHBoxLayout()
            wrap.addStretch()
            wrap.addWidget(badge)
            wrap.addStretch()
            lay.addLayout(wrap)


class CartItemRow(QFrame):
    """장바구니의 한 줄. 수량을 +/- 로 조절하고 삭제할 수 있습니다."""

    qty_changed = pyqtSignal(int, int)     # (행 번호, 증감)
    removed = pyqtSignal(int)              # (행 번호)

    def __init__(self, index: int, line: CartLine, lang: str, won: str, parent=None):
        super().__init__(parent)
        self.index = index
        self.setObjectName("Panel")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(8)

        emoji = QLabel(line.item.emoji)
        emoji.setStyleSheet("font-size:26pt;")

        info = QVBoxLayout()
        info.setSpacing(2)
        name = QLabel(line.describe(lang))
        name.setStyleSheet("font-weight:700;")
        name.setWordWrap(True)
        price = QLabel(f"{line.line_total():,}{won}")
        price.setObjectName("Price")
        info.addWidget(name)
        info.addWidget(price)

        minus = QPushButton("−")
        plus = QPushButton("＋")
        for b in (minus, plus):
            b.setFixedSize(44, 44)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        qty = QLabel(str(line.qty))
        qty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qty.setFixedWidth(34)
        qty.setStyleSheet("font-weight:800;")

        remove = QPushButton("✕")
        remove.setObjectName("Danger")
        remove.setFixedSize(40, 40)
        remove.setCursor(Qt.CursorShape.PointingHandCursor)

        minus.clicked.connect(lambda: self.qty_changed.emit(self.index, -1))
        plus.clicked.connect(lambda: self.qty_changed.emit(self.index, +1))
        remove.clicked.connect(lambda: self.removed.emit(self.index))

        lay.addWidget(emoji)
        lay.addLayout(info, 1)
        lay.addWidget(minus)
        lay.addWidget(qty)
        lay.addWidget(plus)
        lay.addWidget(remove)


class GestureCursor(QLabel):
    """손동작으로 화면 위를 움직이는 반투명 동그라미 커서."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(54, 54)
        self.setText("👆")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            "font-size:30pt; background-color: rgba(45,108,223,0.18);"
            "border:3px solid #2D6CDF; border-radius:27px;")
        # 커서는 클릭/히트테스트 대상이 아님 → 아래 메뉴 카드를 childAt 으로 찾을 수 있게
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.hide()

    def move_norm(self, parent_w: int, parent_h: int, nx: float, ny: float) -> None:
        """0~1 정규화 좌표를 실제 화면 좌표로 바꿔 커서를 옮깁니다."""
        x = int(nx * parent_w) - self.width() // 2
        y = int(ny * parent_h) - self.height() // 2
        self.move(max(0, x), max(0, y))
        if not self.isVisible():
            self.show()
        self.raise_()


class Toast(QLabel):
    """'담았어요' 같은 알림을 잠깐 보여주고 사라지는 말풍선."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            "background-color: rgba(27,35,48,0.92); color:white;"
            "border-radius:22px; padding:14px 28px; font-size:18pt; font-weight:700;")
        self.hide()
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._anim = QPropertyAnimation(self._effect, b"opacity")

    def show_message(self, text: str, parent_w: int, parent_h: int, ms: int = 1400) -> None:
        self.setText(text)
        self.adjustSize()
        self.move((parent_w - self.width()) // 2, int(parent_h * 0.78))
        self.show()
        self.raise_()
        self._effect.setOpacity(1.0)
        QTimer.singleShot(ms, self._fade_out)

    def _fade_out(self) -> None:
        self._anim.stop()
        self._anim.setDuration(400)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self.hide)
        self._anim.start()
