"""
ui/main_window.py — 키오스크 메인 화면 (계획서 3장: 동적 GUI + 상태 머신)
================================================
모든 기능을 하나로 묶는 중심 화면입니다.

화면 전환(상태 머신, QStackedWidget):
  0) 환영 화면  → 1) 메뉴 화면  → 2) 결제 완료 화면

핵심 연동:
  · 비전 스레드의 신호(연령대/얼굴/제스처)를 받아 UI 를 자동 변신
  · 음성 주문 → NLU → 장바구니 자동 구성
  · 단골 인식 → 환영 + 늘 먹던 메뉴 원클릭
  · 손동작 → 카테고리 넘기기 / 담기 / 커서

카메라가 없어도 상단 '시연 도구'의 버튼으로 모든 기능을 시연할 수 있습니다.
"""
from __future__ import annotations

import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (QButtonGroup, QComboBox, QFrame, QGridLayout,
                             QHBoxLayout, QLabel, QMainWindow, QMessageBox,
                             QPushButton, QScrollArea, QSizePolicy, QStackedWidget,
                             QVBoxLayout, QWidget, QInputDialog, QApplication)

import time
from collections import Counter, deque

import config
from core import menu_data
from core.database import KioskDatabase
from core.i18n import Translator, next_lang, LANG_NEXT_LABEL
from core.nlu import parse_order, OrderIntent
from core.order import Cart
from core.regulars import RegularManager
from core.speech import Speaker
from core.vision import VisionThread, _QT
from ui import theme as theme_mod
from ui.widgets import MenuCard, CartItemRow, GestureCursor, Toast, FlowLayout
from ui.voice_dialog import VoiceOrderDialog, SpeechWorker, speech_available

# 화면(상태) 번호
SCREEN_WELCOME = 0
SCREEN_MENU = 1
SCREEN_DONE = 2


class KioskMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # ── 핵심 객체들(OOP 모듈화: 계획서 4.3) ──
        self.db = KioskDatabase()
        self.regulars = RegularManager(self.db)
        self.speaker = Speaker()
        self.tr = Translator(config.DEFAULT_LANGUAGE)
        self.cart = Cart()

        self.mode = config.MODE_STANDARD
        self.current_category = menu_data.CATEGORY_BURGER
        self.set_mode_on = False              # 다음에 담을 때 세트로 담을지
        self.last_embedding: np.ndarray | None = None
        self.active_regular: dict | None = None
        self._order_counter = 1001
        self._auto_mode_locked = False        # 수동으로 모드를 고정했는지
        # 처음부터 True: 얼굴 등장 신호(face_present)의 첫 상승엣지를 놓쳐도
        # 첫 임베딩 프레임에서 반드시 기준 표본을 1개 모으도록 보장합니다.
        self._face_obs_pending = True

        # 연령대 자동 전환 안정화용(다수결 투표 + 쿨다운)
        self._age_votes: deque[str] = deque(maxlen=config.AGE_VOTE_WINDOW)
        self._last_auto_switch_ms = 0.0

        # 손동작 제어: 사용자가 켜고 끕 수 있고, 동작은 쿨다운을 둔다.
        self._gesture_enabled = True          # 손동작 제어 사용 여부(토글)
        self._last_gesture_action_ms = 0.0    # 마지막 동작 실행 시각(쿨다운)
        self._busy = False                    # 결제/대화상자 처리 중 → 중복/제스처 차단
        self._cursor_nx = 0.5                 # 제스처 커서의 최신 정규화 위치(x)
        self._cursor_ny = 0.5                 # 제스처 커서의 최신 정규화 위치(y)
        self._active_voice_dialog = None      # 음성 주문 창 참조(열린 동안 제스처 라우팅)
        self._active_dialog = None            # 팝업/다이얼로그 참조(단골 등록/환영 등)
        self._intro_shown = False             # 시작 접근성 안내를 한 번만 띄우기 위한 플래그
        self._intro_worker: SpeechWorker | None = None   # 접근성 안내의 예/아니오 음성 인식

        self.setWindowTitle(f"{config.APP_TITLE} — {config.TEAM_NAME}")
        self.resize(config.WINDOW_WIDTH, config.WINDOW_HEIGHT)

        self._build_ui()
        self._apply_theme()
        self._start_vision()

        # 무동작 시 첫 화면 복귀 타이머
        self._idle_timer = QTimer(self)
        self._idle_timer.setInterval(config.SESSION_TIMEOUT_MS)
        self._idle_timer.timeout.connect(self._reset_session)
        self._idle_timer.start()

    # ══════════════════════════════════════════
    # 시작 접근성 안내(시각장애인 → 음성 주문 바로가기)
    # ══════════════════════════════════════════
    def showEvent(self, event) -> None:
        """창이 처음 표시될 때 시각장애 여부를 음성으로 물어봅니다(한 번만)."""
        super().showEvent(event)
        if self._intro_shown:
            return
        self._intro_shown = True
        if config.ACCESSIBILITY_INTRO_ENABLED:
            # 창이 먼저 그려진 뒤 안내가 뜨도록 잠깐 미룹니다.
            QTimer.singleShot(900, self._maybe_intro_accessibility)

    def _maybe_intro_accessibility(self) -> None:
        """안내를 띄우기 안전한 상태인지 확인 후 실행(테스트/전환 중이면 건너뜀)."""
        # 오프스크린(자동 테스트)에서는 모달 안내를 띄우지 않습니다.
        if QApplication.platformName() == "offscreen":
            return
        if not self.isVisible() or self._busy:
            return
        if self.stack.currentIndex() != SCREEN_WELCOME or not self.cart.is_empty():
            return
        self._ask_accessibility_intro()

    def _ask_accessibility_intro(self) -> None:
        """시각장애 여부를 음성으로 묻고, '네'면 음성 주문으로 바로 진입합니다.

        · 음성(TTS)으로 질문을 읽어 줍니다.
        · 마이크로 '네/아니요'를 듣고(STT), '네'면 예 버튼을 자동으로 누릅니다.
        · 마이크가 없어도 화면의 예/아니요 버튼(또는 주먹 제스처)으로 응답할 수 있습니다.
        """
        self.speaker.say(self.tr.t("a11y_ask_tts"))

        box = QMessageBox(self)
        box.setWindowTitle("🦯 " + self.tr.t("a11y_ask_title"))
        box.setText(self.tr.t("a11y_ask"))
        # AcceptRole 로 두면 주먹/엄지척 제스처로도 '네'를 누를 수 있습니다.
        yes_btn = box.addButton(self.tr.t("a11y_yes"),
                                QMessageBox.ButtonRole.AcceptRole)
        no_btn = box.addButton(self.tr.t("a11y_no"),
                               QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(no_btn)
        box.setStyleSheet(self.styleSheet())
        self._active_dialog = box            # 제스처 라우팅 대상으로 등록

        # 마이크가 있으면 '네/아니요'를 음성으로도 받습니다(질문 낭독 후 시작).
        if speech_available():
            worker = SpeechWorker(self.tr.lang, self)
            worker.recognized.connect(
                lambda t: self._on_intro_reply(t, box, yes_btn, no_btn))
            self._intro_worker = worker

            def _kick() -> None:
                if self._active_dialog is box and not worker.isRunning():
                    worker.start()
            QTimer.singleShot(config.VOICE_AUTO_LISTEN_DELAY_MS, _kick)

        try:
            box.exec()
            chose_yes = box.clickedButton() is yes_btn
        finally:
            self._active_dialog = None
            if self._intro_worker is not None and self._intro_worker.isRunning():
                self._intro_worker.wait(1500)
            self._intro_worker = None

        if chose_yes:
            # 시각장애인 흐름: 음성 주문 창을 열고 마이크를 자동으로 켭니다.
            self._open_voice_order(auto_listen=True)

    def _on_intro_reply(self, text: str, box, yes_btn, no_btn) -> None:
        """접근성 안내에서 마이크로 들은 답을 예/아니요 버튼 클릭으로 연결."""
        if self._active_dialog is not box:      # 이미 닫혔으면 무시
            return
        if self._is_affirmative(text):
            yes_btn.click()
        elif self._is_negative(text):
            no_btn.click()

    @staticmethod
    def _is_affirmative(text: str) -> bool:
        """'네'에 해당하는 대답인지(한/영/중) 판별."""
        t = (text or "").strip().lower()
        if not t:
            return False
        words = ("맞아", "맞어", "맞습니다", "네", "예", "응", "그래", "당연",
                 "시각장애", "장애", "도와", "그렇", "좋아",
                 "yes", "yeah", "yep", "yup", "correct", "sure", "okay", "ok",
                 "是", "对", "好", "嗯", "需要")
        return any(w in t for w in words)

    @staticmethod
    def _is_negative(text: str) -> bool:
        """'아니요'에 해당하는 대답인지(한/영/중) 판별."""
        t = (text or "").strip().lower()
        if not t:
            return False
        words = ("아니", "아뇨", "괜찮", "됐", "no", "nope", "不", "沒", "没", "不用")
        return any(w in t for w in words)

    # ══════════════════════════════════════════
    # UI 뼈대 구성
    # ══════════════════════════════════════════
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        root.addWidget(self._build_demo_bar())     # 시연용 도구막대

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_welcome_screen())   # 0
        self.stack.addWidget(self._build_menu_screen())      # 1
        self.stack.addWidget(self._build_done_screen())      # 2
        root.addWidget(self.stack, 1)

        root.addWidget(self._build_status_bar())

        # 오버레이: 제스처 커서 + 토스트(부모는 central)
        self.cursor = GestureCursor(central)
        self.toast = Toast(central)

    def _build_header(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("Panel")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 12, 20, 12)

        self.logo = QLabel(f"🍔 {self.tr.t('store_name')}")
        self.logo.setObjectName("Title")
        lay.addWidget(self.logo)
        lay.addStretch()

        # 언어 전환 버튼(계획서 2.4 다국어: 한국어 → English → 中文 순환)
        self.lang_btn = QPushButton(LANG_NEXT_LABEL.get(self.tr.lang, "🌐 English"))
        self.lang_btn.setObjectName("Ghost")
        self.lang_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lang_btn.clicked.connect(self._toggle_language)
        lay.addWidget(self.lang_btn)

        # 음성안내(TTS) 토글
        self.tts_btn = QPushButton("🔊")
        self.tts_btn.setObjectName("Ghost")
        self.tts_btn.setCheckable(True)
        self.tts_btn.setChecked(config.TTS_ENABLED)
        self.tts_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tts_btn.clicked.connect(self._toggle_tts)
        lay.addWidget(self.tts_btn)

        # 손동작 제어 켜기/끄기(주문 중 원치 않는 손동작 오작동 방지)
        self.gesture_btn = QPushButton("✋")
        self.gesture_btn.setObjectName("Ghost")
        self.gesture_btn.setCheckable(True)
        self.gesture_btn.setChecked(True)
        self.gesture_btn.setToolTip(self.tr.t("gesture_tooltip"))
        self.gesture_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.gesture_btn.clicked.connect(self._toggle_gesture)
        lay.addWidget(self.gesture_btn)
        return bar

    def _build_demo_bar(self) -> QWidget:
        """카메라 없이도 모든 기능을 시연하기 위한 도구막대."""
        bar = QFrame()
        bar.setObjectName("StatusBar")
        # 영어·중국어처럼 글자가 길어지면 한 줄을 넘어가므로 자동 줄바꿈(FlowLayout)
        sp = bar.sizePolicy()
        sp.setHeightForWidth(True)
        sp.setVerticalPolicy(QSizePolicy.Policy.Minimum)
        bar.setSizePolicy(sp)
        lay = FlowLayout(bar, spacing=8, alignment="left")
        lay.setContentsMargins(16, 6, 16, 6)

        self.demo_tag = QLabel(self.tr.t("demo_tools"))
        self.demo_tag.setStyleSheet("font-weight:700;")
        lay.addWidget(self.demo_tag)

        # 모드 수동 전환 버튼(텍스트는 _refresh_texts 에서 언어에 맞춰 갱신)
        self.demo_mode_buttons: dict[str, QPushButton] = {}
        self._demo_mode_emoji = {config.MODE_CHILD: "👦", config.MODE_STANDARD: "🧑",
                                 config.MODE_SILVER: "👵", config.MODE_HIGH_CONTRAST: "👁"}
        for mode in (config.MODE_CHILD, config.MODE_STANDARD,
                     config.MODE_SILVER, config.MODE_HIGH_CONTRAST):
            b = QPushButton()
            b.setObjectName("Ghost")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _, m=mode: self._manual_set_mode(m))
            self.demo_mode_buttons[mode] = b
            lay.addWidget(b)

        # 제스처 시뮬레이션
        self.demo_gesture_buttons: dict[str, QPushButton] = {}
        self._demo_gesture_meta = {"swipe_left": ("👈", "prev"),
                                   "swipe_right": ("👉", "next"),
                                   "fist": ("✊", "demo_grab")}
        for g in ("swipe_left", "swipe_right", "fist"):
            b = QPushButton()
            b.setObjectName("Ghost")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _, gg=g: self._handle_gesture_action(gg))
            self.demo_gesture_buttons[g] = b
            lay.addWidget(b)

        self.sim_reg_btn = QPushButton("🙋 " + self.tr.t("demo_regular_sim"))
        self.sim_reg_btn.setObjectName("Ghost")
        self.sim_reg_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sim_reg_btn.clicked.connect(self._simulate_regular)
        lay.addWidget(self.sim_reg_btn)

        self._refresh_demo_bar_texts()
        return bar

    def _refresh_demo_bar_texts(self) -> None:
        """시연 도구막대의 글자를 현재 언어로 갱신."""
        self.demo_tag.setText(self.tr.t("demo_tools"))
        mode_key = {config.MODE_CHILD: "child_mode", config.MODE_STANDARD: "standard_mode",
                    config.MODE_SILVER: "silver_mode", config.MODE_HIGH_CONTRAST: "contrast_mode"}
        for mode, b in self.demo_mode_buttons.items():
            b.setText(f"{self._demo_mode_emoji[mode]} {self.tr.t(mode_key[mode])}")
        for g, b in self.demo_gesture_buttons.items():
            emoji, key = self._demo_gesture_meta[g]
            b.setText(f"{emoji} {self.tr.t(key)}")
        self.sim_reg_btn.setText("🙋 " + self.tr.t("demo_regular_sim"))

    # ── 환영 화면 ──
    def _build_welcome_screen(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(40, 30, 40, 30)
        lay.setSpacing(18)
        lay.addStretch()

        self.welcome_title = QLabel(self.tr.t("welcome_title"))
        self.welcome_title.setObjectName("Title")
        self.welcome_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.welcome_sub = QLabel(self.tr.t("welcome_sub"))
        self.welcome_sub.setObjectName("SubTitle")
        self.welcome_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.welcome_title)
        lay.addWidget(self.welcome_sub)

        # 베스트셀러 미리보기(실버 모드 4종 전면 노출 컨셉)
        # 영어·중국어에서 이름이 길어져도 잘리지 않도록 자동 줄바꿈(FlowLayout)
        best_box = QWidget()
        sp = best_box.sizePolicy()
        sp.setHeightForWidth(True)
        sp.setVerticalPolicy(QSizePolicy.Policy.Minimum)
        best_box.setSizePolicy(sp)
        best_row = FlowLayout(best_box, spacing=10, alignment="center")
        self.best_label = QLabel("🔥 " + self.tr.t("best_menu"))
        self.best_chips: list[tuple[QLabel, menu_data.MenuItem]] = []
        for m in menu_data.best_sellers()[:4]:
            chip = QLabel(f"{m.emoji} {m.name(self.tr.lang)}")
            chip.setObjectName("Badge")
            self.best_chips.append((chip, m))
            best_row.addWidget(chip)

        lay.addSpacing(10)
        lay.addWidget(best_box)
        lay.addSpacing(20)

        self.start_btn = QPushButton("🛎  " + self.tr.t("start_order"))
        self.start_btn.setObjectName("Primary")
        self.start_btn.setMinimumSize(360, 90)
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.clicked.connect(lambda: self._go_menu())
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(self.start_btn)
        row.addStretch()
        lay.addLayout(row)

        # 환영 화면 음성 주문 버튼 — 첫 화면에서 바로 말로 주문 시작
        self.welcome_voice_btn = QPushButton("🎤  " + self.tr.t("voice_order"))
        self.welcome_voice_btn.setObjectName("Ghost")
        self.welcome_voice_btn.setMinimumSize(240, 60)
        self.welcome_voice_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.welcome_voice_btn.clicked.connect(self._open_voice_order)
        vrow = QHBoxLayout()
        vrow.addStretch()
        vrow.addWidget(self.welcome_voice_btn)
        vrow.addStretch()
        lay.addLayout(vrow)

        lay.addStretch()
        return w

    # ── 메뉴 화면 ──
    def _build_menu_screen(self) -> QWidget:
        w = QWidget()
        outer = QHBoxLayout(w)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(16)

        # 왼쪽: 카테고리 탭 + 메뉴 그리드
        left = QVBoxLayout()
        left.setSpacing(12)

        self.cat_bar = QHBoxLayout()
        self.cat_buttons: dict[str, QPushButton] = {}
        self.cat_group = QButtonGroup(self)
        for cat in menu_data.CATEGORY_ORDER:
            b = QPushButton()
            b.setCheckable(True)
            b.setObjectName("Ghost")
            b.setMinimumHeight(56)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _, c=cat: self._select_category(c))
            self.cat_buttons[cat] = b
            self.cat_group.addButton(b)
            self.cat_bar.addWidget(b)
        left.addLayout(self.cat_bar)

        # 세트/단품 토글
        opt_row = QHBoxLayout()
        self.set_toggle = QPushButton()
        self.set_toggle.setCheckable(True)
        self.set_toggle.setObjectName("Ghost")
        self.set_toggle.setMinimumHeight(46)
        self.set_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_toggle.clicked.connect(self._toggle_set)
        opt_row.addWidget(self.set_toggle)

        self.voice_btn = QPushButton()
        self.voice_btn.setObjectName("Primary")
        self.voice_btn.setMinimumHeight(46)
        self.voice_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.voice_btn.clicked.connect(self._open_voice_order)
        opt_row.addWidget(self.voice_btn)
        left.addLayout(opt_row)

        # 메뉴 그리드(스크롤 영역)
        self.menu_scroll = QScrollArea()
        self.menu_scroll.setWidgetResizable(True)
        self.menu_host = QWidget()
        self.menu_grid = QGridLayout(self.menu_host)
        self.menu_grid.setSpacing(14)
        self.menu_scroll.setWidget(self.menu_host)
        left.addWidget(self.menu_scroll, 1)

        outer.addLayout(left, 2)

        # 오른쪽: 장바구니 패널
        outer.addWidget(self._build_cart_panel(), 1)
        return w

    def _build_cart_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Card")
        panel.setMinimumWidth(380)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(10)

        self.cart_title = QLabel()
        self.cart_title.setObjectName("CartTitle")
        lay.addWidget(self.cart_title)

        self.cart_scroll = QScrollArea()
        self.cart_scroll.setWidgetResizable(True)
        self.cart_host = QWidget()
        self.cart_list = QVBoxLayout(self.cart_host)
        self.cart_list.setSpacing(8)
        self.cart_list.addStretch()
        self.cart_scroll.setWidget(self.cart_host)
        lay.addWidget(self.cart_scroll, 1)

        self.total_label = QLabel()
        self.total_label.setObjectName("Title")
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        lay.addWidget(self.total_label)

        btn_row = QHBoxLayout()
        self.clear_btn = QPushButton()
        self.clear_btn.setObjectName("Danger")
        self.clear_btn.setMinimumHeight(56)
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.clicked.connect(self._clear_cart)
        self.checkout_btn = QPushButton()
        self.checkout_btn.setObjectName("Primary")
        self.checkout_btn.setMinimumHeight(56)
        self.checkout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.checkout_btn.clicked.connect(self._checkout)
        btn_row.addWidget(self.clear_btn)
        btn_row.addWidget(self.checkout_btn, 1)
        lay.addLayout(btn_row)
        return panel

    # ── 결제 완료 화면 ──
    def _build_done_screen(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(16)

        self.done_emoji = QLabel("✅")
        self.done_emoji.setStyleSheet("font-size:90pt;")
        self.done_emoji.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.done_title = QLabel()
        self.done_title.setObjectName("Title")
        self.done_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.done_number = QLabel()
        self.done_number.setObjectName("SubTitle")
        self.done_number.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.done_emoji)
        lay.addWidget(self.done_title)
        lay.addWidget(self.done_number)
        return w

    # ── 하단 상태바 ──
    def _build_status_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("StatusBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(18, 8, 18, 8)
        lay.setSpacing(18)

        self.mode_label = QLabel()
        self._vision_status_key = "vision_preparing"
        self.vision_label = QLabel(self.tr.t(self._vision_status_key))
        self.gesture_label = QLabel("✋ —")
        lay.addWidget(self.mode_label)
        lay.addWidget(self.vision_label)
        lay.addWidget(self.gesture_label)
        lay.addStretch()

        # 카메라 미리보기(작게)
        self.cam_view = QLabel()
        self.cam_view.setFixedSize(160, 120)
        self.cam_view.setStyleSheet("border:2px solid #2D6CDF; border-radius:8px;")
        self.cam_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cam_view.setText("CAM")
        lay.addWidget(self.cam_view)
        return bar

    # ══════════════════════════════════════════
    # 테마 / 언어
    # ══════════════════════════════════════════
    def _apply_theme(self) -> None:
        theme = theme_mod.get_theme(self.mode)
        self.setStyleSheet(theme_mod.get_stylesheet(theme))
        names = {config.MODE_STANDARD: self.tr.t("standard_mode"),
                 config.MODE_SILVER: self.tr.t("silver_mode"),
                 config.MODE_CHILD: self.tr.t("child_mode"),
                 config.MODE_HIGH_CONTRAST: self.tr.t("contrast_mode")}
        self.mode_label.setText("🎨 " + names.get(self.mode, ""))
        self._refresh_texts()

    def _refresh_texts(self) -> None:
        """언어/모드에 맞춰 모든 글자를 새로고침."""
        self.logo.setText(f"🍔 {self.tr.t('store_name')}")
        self.welcome_title.setText(self.tr.t("welcome_title"))
        self.welcome_sub.setText(self.tr.t("welcome_sub"))
        self.start_btn.setText("🛎  " + self.tr.t("start_order"))
        self.welcome_voice_btn.setText("🎤  " + self.tr.t("voice_order"))
        self.cart_title.setText("🛒 " + self.tr.t("cart"))
        self.clear_btn.setText("🗑 " + self.tr.t("clear"))
        self.voice_btn.setText("🎤 " + self.tr.t("voice_order"))
        self.lang_btn.setText(LANG_NEXT_LABEL.get(self.tr.lang, "🌐 English"))
        self.gesture_btn.setToolTip(self.tr.t("gesture_tooltip"))
        self.best_label.setText("🔥 " + self.tr.t("best_menu"))
        for chip, m in self.best_chips:
            chip.setText(f"{m.emoji} {m.name(self.tr.lang)}")
        self._set_vision_status(self._vision_status_key)
        self._refresh_demo_bar_texts()
        labels = menu_data.CATEGORY_LABELS[self.tr.lang]
        for cat, b in self.cat_buttons.items():
            b.setText(labels[cat])
        self._update_set_toggle_text()
        self._refresh_menu_grid()
        self._refresh_cart()

    def _toggle_language(self) -> None:
        self.tr.set_lang(next_lang(self.tr.lang))
        self._apply_theme()

    def _toggle_tts(self) -> None:
        on = self.tts_btn.isChecked()
        self.speaker.toggle(on)
        self.tts_btn.setText("🔊" if on else "🔈")

    def _toggle_gesture(self) -> None:
        """손동작 제어를 켜고 끕니다(원치 않는 손동작 오작동 방지)."""
        self._gesture_enabled = self.gesture_btn.isChecked()
        self.gesture_btn.setText("✋" if self._gesture_enabled else "🚫")
        if not self._gesture_enabled:
            self.cursor.hide()
            self.gesture_label.setText("✋ " + self.tr.t("gesture_off"))
        self._show_toast(self.tr.t("gesture_on_toast") if self._gesture_enabled
                         else self.tr.t("gesture_off_toast"))

    def _manual_set_mode(self, mode: str) -> None:
        """시연 버튼으로 모드를 직접 바꿉니다(자동 전환 잠금)."""
        self._auto_mode_locked = True
        self._set_mode(mode, announce=True)

    def _set_mode(self, mode: str, announce: bool = False) -> None:
        if mode == self.mode:
            return
        self.mode = mode
        self._apply_theme()
        if announce:
            say_key = {config.MODE_SILVER: "mode_silver_say",
                       config.MODE_CHILD: "mode_child_say",
                       config.MODE_HIGH_CONTRAST: "mode_contrast_say",
                       config.MODE_STANDARD: "mode_standard_say"}
            self.speaker.say(self.tr.t(say_key.get(mode, "mode_standard_say")))
            self._show_toast(theme_mod.get_theme(mode).name.upper() + " MODE")

    # ══════════════════════════════════════════
    # 화면 전환(상태 머신)
    # ══════════════════════════════════════════
    def _go_menu(self) -> None:
        self._reset_idle()
        self._select_category(menu_data.CATEGORY_BURGER)
        self.stack.setCurrentIndex(SCREEN_MENU)

    def _select_category(self, cat: str) -> None:
        self.current_category = cat
        self.cat_buttons[cat].setChecked(True)
        self._refresh_menu_grid()
        self._reset_idle()

    def _refresh_menu_grid(self) -> None:
        # 기존 카드 제거
        while self.menu_grid.count():
            item = self.menu_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        won = self.tr.t("won")
        # 실버 모드: 베스트셀러를 앞쪽에 노출, 한 줄에 2개(큰 카드)
        items = menu_data.items_in_category(self.current_category)
        if self.mode == config.MODE_SILVER:
            items = sorted(items, key=lambda m: (not m.is_best, m.name_ko))
            cols = 2
        elif self.mode == config.MODE_CHILD:
            cols = 2
        else:
            cols = 3
        for i, item in enumerate(items):
            card = MenuCard(item, self.tr.lang, won)
            card.clicked.connect(lambda _, it=item: self._add_to_cart(it))
            self.menu_grid.addWidget(card, i // cols, i % cols)

    def _toggle_set(self) -> None:
        self.set_mode_on = self.set_toggle.isChecked()
        self._update_set_toggle_text()

    def _update_set_toggle_text(self) -> None:
        if self.set_mode_on:
            self.set_toggle.setText("✅ " + self.tr.t("set_toggle"))
            self.set_toggle.setChecked(True)
        else:
            self.set_toggle.setText("⬜ " + self.tr.t("set_toggle"))
            self.set_toggle.setChecked(False)

    # ══════════════════════════════════════════
    # 장바구니
    # ══════════════════════════════════════════
    def _add_to_cart(self, item: menu_data.MenuItem, qty: int = 1,
                     is_set: bool | None = None, drink_size: str = "M") -> None:
        is_set = self.set_mode_on if is_set is None else is_set
        # 버거가 아니면 세트 개념 없음
        if item.category != menu_data.CATEGORY_BURGER:
            is_set = False
        self.cart.add(item, qty=qty, is_set=is_set, drink_size=drink_size)
        self._refresh_cart()
        self._show_toast(f"{item.emoji} {item.name(self.tr.lang)} {self.tr.t('added_toast')}")
        say_key = "said_set_added" if is_set else "said_added"
        self.speaker.say(f"{item.name(self.tr.lang)} {self.tr.t(say_key)}")
        self._reset_idle()

    def _refresh_cart(self) -> None:
        # 기존 줄 제거(마지막 stretch 는 유지)
        while self.cart_list.count() > 1:
            item = self.cart_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        won = self.tr.t("won")
        if self.cart.is_empty():
            empty = QLabel("🧺 " + self.tr.t("cart_empty"))
            empty.setObjectName("SubTitle")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cart_list.insertWidget(0, empty)
        else:
            for idx, line in enumerate(self.cart.lines):
                row = CartItemRow(idx, line, self.tr.lang, won)
                row.qty_changed.connect(self._on_cart_qty)
                row.removed.connect(self._on_cart_remove)
                self.cart_list.insertWidget(idx, row)
        self.total_label.setText(f"{self.tr.t('total')}: {self.cart.total():,}{won}")
        self.checkout_btn.setText(
            f"💳 {self.tr.t('checkout')} ({self.cart.item_count()})")

    def _on_cart_qty(self, idx: int, delta: int) -> None:
        self.cart.change_qty(idx, delta)
        self._refresh_cart()
        self._reset_idle()

    def _on_cart_remove(self, idx: int) -> None:
        self.cart.remove_index(idx)
        self._refresh_cart()
        self._reset_idle()

    def _clear_cart(self) -> None:
        self.cart.clear()
        self._refresh_cart()
        self._reset_idle()

    # ══════════════════════════════════════════
    # 음성 주문(NLU)
    # ══════════════════════════════════════════
    def _open_voice_order(self, auto_listen: bool = False) -> None:
        was_welcome = self.stack.currentIndex() == SCREEN_WELCOME
        dlg = VoiceOrderDialog(self.tr.lang, self.tr.t("voice_hint"),
                               self.tr.t("listening"), self,
                               speaker=self.speaker, auto_listen=auto_listen)
        dlg.setStyleSheet(self.styleSheet())
        self._active_voice_dialog = dlg          # 제스처 라우팅을 위해 참조 저장
        if dlg.exec():
            text = dlg.get_text()
            if text:
                self._process_order_text(text)
                # 환영 화면에서 열었고 메뉴가 담겼으면 메뉴 화면으로 자동 이동
                if was_welcome and not self.cart.is_empty():
                    self._go_menu()
        self._active_voice_dialog = None         # 창 닫힘 → 참조 해제
        self._reset_idle()

    def _process_order_text(self, text: str) -> None:
        result = parse_order(text)
        # 다국어: 영어로 말하면 UI 전체를 영어로 전환(계획서 2.4)
        if result.detected_language != self.tr.lang:
            self.tr.set_lang(result.detected_language)
            self._apply_theme()
        added = 0
        handled = False        # 결제/비우기 같은 '명령'도 처리한 것으로 인정
        for intent in result.intents:
            added += self._apply_intent(intent)
            if intent.action in ("clear", "checkout"):
                handled = True
        self._refresh_cart()
        engine = self.tr.t("engine_llm") if result.used_llm else self.tr.t("engine_smart")
        if added:
            self._show_toast(f"🎤 {engine}: {self.tr.t('voice_added').format(n=added)}")
        elif not handled:
            self._show_toast("🤔 " + self.tr.t("not_understood"))

    def _apply_intent(self, intent: OrderIntent) -> int:
        """NLU 가 만든 의도 1개를 장바구니에 반영. 담은 개수를 반환."""
        if intent.action == "clear":
            self._clear_cart()
            return 0
        if intent.action == "checkout":
            QTimer.singleShot(400, self._checkout)
            return 0
        item = menu_data.get_item(intent.item_id) if intent.item_id else None
        if not item:
            return 0
        is_set = intent.is_set and item.category == menu_data.CATEGORY_BURGER
        # 세트의 음료/사이드 '종류 변경'은 세트 한 줄에 표기합니다.
        # (별도 라인으로 또 담으면 세트값 + 단품값이 이중 청구되므로 금지)
        drink_id = intent.drink_id if (is_set and intent.drink_id) else None
        side_id = intent.side_id if (is_set and intent.side_id) else None
        self.cart.add(item, qty=intent.qty, is_set=is_set,
                      drink_size=intent.drink_size,
                      drink_id=drink_id, side_id=side_id)
        return intent.qty

    # ══════════════════════════════════════════
    # 결제 / 단골
    # ══════════════════════════════════════════
    def _checkout(self) -> None:
        if self.cart.is_empty():
            self._show_toast("🧺 " + self.tr.t("cart_empty"))
            return
        if self._busy:            # 이미 결제 처리 중이면 중복 실행 차단(대화상자 2개 방지)
            return
        self._busy = True
        # 판매 통계 저장(계획서 6장 빅데이터)
        self.db.record_order(self.cart.to_records(), self.cart.total())

        # 단골 등록 제안(새 손님이고 얼굴이 잡혀 있을 때)
        if self.active_regular is None and self.last_embedding is not None:
            self._offer_regular_registration()
        elif self.active_regular is not None:
            # 단골이면 즐겨찾기 갱신
            self.regulars.update_favorite(self.active_regular["id"],
                                          self.cart.snapshot_favorite())

        self._order_counter += 1
        self.done_title.setText("🎉 " + self.tr.t("thank_you"))
        self.done_number.setText(f"{self.tr.t('order_number')}: {self._order_counter}")
        self.speaker.say(self.tr.t("thank_you"))
        self.stack.setCurrentIndex(SCREEN_DONE)
        QTimer.singleShot(3500, self._reset_session)

    def _offer_regular_registration(self) -> None:
        ask = QMessageBox(self)
        ask.setWindowTitle(self.tr.t("register_regular"))
        ask.setText("🙋 " + self.tr.t("regular_register_ask"))
        ask.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        ask.setStyleSheet(self.styleSheet())
        self._active_dialog = ask
        try:
            if ask.exec() == QMessageBox.StandardButton.Yes:
                suggested = self.regulars.suggest_nickname(self.tr.t("regular_nick_base"))
                nickname, ok = QInputDialog.getText(
                    self, self.tr.t("register_regular"),
                    self.tr.t("choose_nickname"),
                    text=suggested)
                if ok and nickname.strip():
                    self.regulars.register(nickname.strip(), self.last_embedding,
                                           self.cart.snapshot_favorite())
                    self._show_toast("⭐ " + self.tr.t("registered_done").format(name=nickname))
        finally:
            self._active_dialog = None

    def _show_regular_welcome(self, regular: dict) -> None:
        """단골 인식 시 환영 + 늘 먹던 메뉴 원클릭 제안(계획서 2.2)."""
        if self._busy:                       # 다른 대화상자 처리 중이면 중복 표시 방지
            return
        if self.active_regular and self.active_regular["id"] == regular["id"]:
            return
        self.active_regular = regular
        self._busy = True
        nickname = regular["nickname"]
        greet = (f"{nickname}{self.tr.t('regular_welcome')} {self.tr.t('regular_ask')}")
        self.speaker.say(greet)

        box = QMessageBox(self)
        box.setWindowTitle("⭐ " + nickname)
        fav = regular.get("favorite")
        fav_cart = Cart.from_favorite(fav) if fav else Cart()
        detail = ", ".join(l.describe(self.tr.lang) for l in fav_cart.lines) or "-"
        box.setText(f"⭐ {nickname}{self.tr.t('regular_welcome')}\n\n"
                    f"{self.tr.t('regular_ask')}\n🍔 {detail}")
        yes = box.addButton(self.tr.t("yes_same"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(self.tr.t("no_new"), QMessageBox.ButtonRole.RejectRole)
        box.setStyleSheet(self.styleSheet())
        self._active_dialog = box
        try:
            box.exec()
            if box.clickedButton() == yes and not fav_cart.is_empty():
                self.cart = fav_cart
                self._go_menu()
                self._refresh_cart()
                self._show_toast("⚡ " + self.tr.t("usual_ready"))
        finally:
            self._active_dialog = None
            self._busy = False               # 환영 대화상자 종료 → 처리 플래그 해제

    # ══════════════════════════════════════════
    # 비전 신호 처리
    # ══════════════════════════════════════════
    def _start_vision(self) -> None:
        if not (_QT and config.VISION_ENABLED):
            self._set_vision_status("vision_demo")
            return
        self.vision = VisionThread()
        self.vision.status.connect(self._on_vision_status)
        self.vision.age_group.connect(self._on_age_group)
        self.vision.face_embedding.connect(self._on_face_embedding)
        self.vision.face_present.connect(self._on_face_present)
        self.vision.gesture.connect(self._on_gesture)
        self.vision.frame_ready.connect(self._on_frame)
        self.vision.start()

    def _set_vision_status(self, key: str) -> None:
        """비전 상태 키를 기억하고 현재 언어로 표시(언어 전환 시 재번역용)."""
        self._vision_status_key = key
        self.vision_label.setText(self.tr.t(key))

    def _on_vision_status(self, key: str) -> None:
        """비전 스레드가 보낸 상태 키를 화면에 표시."""
        self._set_vision_status(key)

    def _on_age_group(self, group: str) -> None:
        """연령대 추정 → 자동 모드 전환(계획서 2.1).

        한 프레임의 추정값은 흔들리기 때문에 그대로 쓰면 화면이 깜빡입니다.
        그래서 ① 최근 여러 프레임을 모아 '다수결'로 결정하고,
        ② 모드를 바꾼 직후 잠깐(쿨다운) 동안은 다시 바꾸지 않아 안정적으로 만듭니다.
        """
        if config.FACE_DEBUG and config.VISION_ENABLED:
            now_dbg = time.time()
            if now_dbg - getattr(self, "_dbg_age_last", 0.0) > 1.0:
                self._dbg_age_last = now_dbg
                tally = dict(Counter(self._age_votes))
                print(f"[연령진단] 추정={group} 자동잠금={self._auto_mode_locked} "
                      f"현재모드={self.mode} 투표={tally}", flush=True)
        if self._auto_mode_locked:
            return

        # ① 최근 추정값을 투표함에 모읍니다.
        self._age_votes.append(group)
        if len(self._age_votes) < config.AGE_VOTE_MIN_COUNT:
            return

        # 가장 많이 나온 연령대와 그 표 수를 구합니다.
        winner, count = Counter(self._age_votes).most_common(1)[0]
        if count < config.AGE_VOTE_MIN_COUNT:
            return                     # 과반에 못 미치면 아직 확정하지 않음

        mapping = {"senior": config.MODE_SILVER,
                   "child": config.MODE_CHILD,
                   "adult": config.MODE_STANDARD}
        target_mode = mapping.get(winner, config.MODE_STANDARD)
        if target_mode == self.mode:
            return                     # 이미 그 모드면 전환 불필요

        # ② 쿨다운: 직전 전환 후 일정 시간이 지나야 다시 전환합니다.
        now = time.time() * 1000
        if now - self._last_auto_switch_ms < config.AGE_MODE_COOLDOWN_MS:
            return
        self._last_auto_switch_ms = now
        self._set_mode(target_mode, announce=True)

    def _on_face_embedding(self, emb: np.ndarray) -> None:
        # 얼굴 임베딩은 등록 흐름(단골 등록 시 그 사람의 얼굴 저장)에서만 씁니다.
        # 카메라로 '누구인지' 자동 판별해 단골 환영을 띄우던 기능은 제거했습니다.
        # 이유: MediaPipe 랜드마크 임베딩은 서로 다른 사람도 코사인 0.99로 거의
        # 똑같이 나와(콘솔 [얼굴진단]으로 실측 확인) 다른 손님을 단골로 오인식했습니다.
        # 카메라 인식의 '대상'은 이제 개인 신원이 아니라 연령대(어린이/성인/노인)입니다.
        self.last_embedding = emb

    def _on_face_present(self, present: bool) -> None:
        if present:
            self._face_obs_pending = True   # 새 얼굴 등장 → 기준 표본 1개 수집 예약
            return
        if not present:
            if self._busy:    # 대화상자 처리 중엔 추적 상태를 유지(환영 재발동 방지)
                return
            self.active_regular = None
            self.regulars.reset_tracking()
            self._age_votes.clear()       # 손님이 떠나면 투표함 초기화

    def _on_gesture(self, name: str, x: float, y: float) -> None:
        # 손동작이 꺼져 있으면 모두 무시
        if not self._gesture_enabled:
            self.cursor.hide()
            self.gesture_label.setText("✋ " + self.tr.t("gesture_off"))
            return
        # 음성 주문 창이 열려 있으면 제스처를 다이얼로그로 라우팅(배경 오작동 방지)
        if self._active_voice_dialog is not None:
            if name in ("swipe_left", "swipe_right", "fist", "sign_yes"):
                now = time.time() * 1000
                if now - self._last_gesture_action_ms < config.GESTURE_ACTION_COOLDOWN_MS:
                    return
                self._last_gesture_action_ms = now
                self._active_voice_dialog.receive_gesture(name)
            return
        # 팝업/다이얼로그이 열려 있으면 제스처를 팝업으로 라우팅
        if self._active_dialog is not None:
            if name in ("fist", "sign_yes", "swipe_left", "swipe_right"):
                now = time.time() * 1000
                if now - self._last_gesture_action_ms < config.GESTURE_ACTION_COOLDOWN_MS:
                    return
                self._last_gesture_action_ms = now
                self._handle_dialog_gesture(name)
            return
        # 결제/단골 대화상자 처리 중이면 제스처 차단
        if self._busy:
            self.cursor.hide()
            return
        self.gesture_label.setText(f"✋ {name}")
        # 가리키기/펼침일 때만 커서를 옮긴다. 주먹을 쥘 때는 '마지막으로 가리킨
        # 위치'를 그대로 사용해, 가리키던 그 메뉴를 정확히 담는다(커서 점프 방지).
        if name in ("point", "open_palm"):
            self._cursor_nx, self._cursor_ny = x, y   # 커서 위치 기억(주먹 담기에 사용)
            central = self.centralWidget()
            self.cursor.move_norm(central.width(), central.height(), x, y)
            return
        if name == "fist_hold":
            return                                    # 쥐는 중 → 커서 위치 유지
        # 실제 '동작' 제스처만, 일정 간격(쿨다운)을 두고 한 번씩 실행 → 연속 오작동 차단
        if name not in ("swipe_left", "swipe_right", "fist", "sign_yes"):
            return
        now = time.time() * 1000
        if now - self._last_gesture_action_ms < config.GESTURE_ACTION_COOLDOWN_MS:
            return
        self._last_gesture_action_ms = now
        self._handle_gesture_action(name)

    def _handle_dialog_gesture(self, name: str) -> None:
        """팝업에서 제스처를 버튼 클릭으로 변환"""
        if self._active_dialog is None:
            return
        # 주먹 쥐기 / 엄지척 → Yes/Accept 버튼 클릭
        if name in ("fist", "sign_yes"):
            yes_btn = self._active_dialog.button(QMessageBox.StandardButton.Yes)
            if yes_btn:
                yes_btn.click()
            else:
                # 커스텀 버튼이면 AcceptRole 찾기
                for btn in self._active_dialog.buttons():
                    if self._active_dialog.buttonRole(btn) == QMessageBox.ButtonRole.AcceptRole:
                        btn.click()
                        break
        # 손가락 왼쪽 / 오른쪽 스와이프 → 없음(팝업에서는 무시)
        # 향후 확장: 버튼이 여러 개인 경우 스와이프로 선택 가능
        elif name in ("swipe_left", "swipe_right"):
            # 현재는 무시하지만, 향후 다중 버튼 네비게이션 지원 가능
            pass

    def _handle_gesture_action(self, name: str) -> None:
        if self.stack.currentIndex() != SCREEN_MENU:
            if name == "sign_yes" and self.stack.currentIndex() == SCREEN_WELCOME:
                self._go_menu()
            return
        cats = menu_data.CATEGORY_ORDER
        idx = cats.index(self.current_category)
        if name == "swipe_right":
            self._select_category(cats[(idx + 1) % len(cats)])
            self._show_toast("👉 " + self.tr.t("next"))
        elif name == "swipe_left":
            self._select_category(cats[(idx - 1) % len(cats)])
            self._show_toast("👈 " + self.tr.t("prev"))
        elif name == "fist":
            # 커서가 가리키는 메뉴를 담는다(가리킨 게 없으면 안내, 커서가 없으면 베스트)
            item = self._menu_item_under_cursor()
            if item is not None:
                self._add_to_cart(item)
            elif not self.cursor.isHidden():
                self._show_toast(self.tr.t("point_then_fist"))
            else:
                items = menu_data.items_in_category(self.current_category)
                if items:
                    target = next((m for m in items if m.is_best), items[0])
                    self._add_to_cart(target)
        elif name == "sign_yes":
            self._checkout()
        self._reset_idle()

    def _menu_item_under_cursor(self) -> menu_data.MenuItem | None:
        """제스처 커서가 놓인 위치의 메뉴 카드를 찾아 그 상품을 돌려줍니다."""
        if self.stack.currentIndex() != SCREEN_MENU:
            return None
        central = self.centralWidget()
        if central is None:
            return None
        px = int(self._cursor_nx * central.width())
        py = int(self._cursor_ny * central.height())
        w = central.childAt(px, py)
        while w is not None:
            if isinstance(w, MenuCard):
                return w.item
            w = w.parentWidget()
        return None

    def _on_frame(self, frame) -> None:
        """카메라 미리보기를 상태바에 표시."""
        try:
            import cv2
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            img = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
            pix = QPixmap.fromImage(img).scaled(
                self.cam_view.width(), self.cam_view.height(),
                Qt.AspectRatioMode.KeepAspectRatio)
            self.cam_view.setPixmap(pix)
        except Exception:
            pass

    # ══════════════════════════════════════════
    # 단골 시뮬레이션(시연용)
    # ══════════════════════════════════════════
    def _simulate_regular(self) -> None:
        """카메라 없이 단골 기능을 시연. 없으면 샘플 단골을 즉석 생성."""
        regs = self.regulars._regulars
        if not regs:
            # 샘플 단골 자동 생성(치즈버거매니아)
            sample = Cart()
            sample.add(menu_data.get_item("burger_double_cheese"), is_set=True, drink_size="L")
            sample.add(menu_data.get_item("side_fries"))
            # 실제 얼굴 임베딩처럼 '단위 벡터'로 만든 가상 얼굴(기준 평균을 망치지 않도록)
            rng = np.random.default_rng(7)
            emb = rng.standard_normal(72)
            emb = emb / np.linalg.norm(emb)
            self.last_embedding = emb
            self.regulars.register(self.tr.t("sample_regular"), emb, sample.snapshot_favorite())
            regs = self.regulars._regulars
        self.active_regular = None
        self.regulars.reset_tracking()
        self._show_regular_welcome(regs[0])

    # ══════════════════════════════════════════
    # 유틸 / 세션 관리
    # ══════════════════════════════════════════
    def _show_toast(self, text: str) -> None:
        central = self.centralWidget()
        self.toast.show_message(text, central.width(), central.height())

    def _reset_idle(self) -> None:
        self._idle_timer.start()

    def _reset_session(self) -> None:
        """무동작 시 처음 화면으로(다음 손님 준비)."""
        self.cart.clear()
        self.active_regular = None
        self.regulars.reset_tracking()
        self.set_mode_on = False
        self._auto_mode_locked = False
        self._age_votes.clear()           # 다음 손님을 위해 투표함 초기화
        self._busy = False                # 결제/대화 처리 플래그 해제
        self._update_set_toggle_text()
        self._refresh_cart()
        self.stack.setCurrentIndex(SCREEN_WELCOME)

    def closeEvent(self, event) -> None:
        try:
            if hasattr(self, "vision"):
                self.vision.stop()
        except Exception:
            pass
        self.speaker.shutdown()
        self.db.close()
        super().closeEvent(event)
