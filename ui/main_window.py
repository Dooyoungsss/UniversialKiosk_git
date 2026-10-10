"""
ui/main_window.py — 키오스크 메인 화면 (계획서 3장: 동적 GUI + 상태 머신)
================================================
모든 기능을 하나로 묶는 중심 화면입니다.

화면 전환(상태 머신, QStackedWidget):
  0) 환영 화면  → 1) 메뉴 화면  → 2) 결제 완료 화면

5대 핵심 기능 연동:
  ① 제스처       : 손바닥 커서(에임) → 핀치·드웰로 선택, 좌우 스와이프로 카테고리 넘기기
  ② 연령 자동 화면 : 비전 스레드의 연령대 신호 → 다수결·쿨다운 → 어린이·일반·실버 모드
  ③ 음성         : 눈이 불편한 손님 안내 → 음성 주문(STT→NLU) → 담은 결과를 소리로 안내(TTS)
  ④ 다국어       : 한국어·영어·중국어 전환(말한 언어로 화면 자동 전환)
  ⑤ 고대비       : 아래쪽 접근성 버튼 / 접근성 안내 '네' → 검정·노랑 고대비 화면

화면은 LG 스탠바이미(27ART10DKPL) 세로 1080×1920 에 맞춘 세로 전용 배치입니다.

카메라가 없어도 상단 '시연 도구'의 버튼으로 모든 기능을 시연할 수 있습니다.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (QButtonGroup, QComboBox, QFrame, QGridLayout,
                             QHBoxLayout, QLabel, QMainWindow,
                             QPushButton, QScrollArea, QSizePolicy, QStackedWidget,
                             QVBoxLayout, QWidget, QApplication)

import time
from collections import Counter, deque

import config
from core import menu_data
from core.database import KioskDatabase
from core.i18n import Translator, next_lang, LANG_NEXT_LABEL
from core.nlu import parse_order, OrderIntent
from core.order import Cart
from core.speech import Speaker
from core.vision import VisionThread, _QT
from ui import theme as theme_mod
from ui.widgets import (MenuCard, CartItemRow, GestureCursor, Toast, FlowLayout,
                        ChoiceDialog)
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
        self.speaker = Speaker()
        self.tr = Translator(config.DEFAULT_LANGUAGE)
        self.cart = Cart()

        self.mode = config.MODE_STANDARD
        self._mode_before_contrast = config.MODE_STANDARD   # 고대비를 끌 때 돌아갈 화면
        self.current_category = menu_data.CATEGORY_BURGER
        self.set_mode_on = False              # 다음에 담을 때 세트로 담을지
        self._order_counter = 1001
        self._auto_mode_locked = False        # 수동으로 모드를 고정했는지

        # 연령대 자동 전환 안정화용(다수결 투표 + 쿨다운)
        self._age_votes: deque[str] = deque(maxlen=config.AGE_VOTE_WINDOW)
        self._last_auto_switch_ms = 0.0

        # 손동작 제어: 사용자가 켜고 끕 수 있고, 동작은 쿨다운을 둔다.
        self._gesture_enabled = True          # 손동작 제어 사용 여부(토글)
        self._last_gesture_action_ms = 0.0    # 마지막 동작 실행 시각(쿨다운)
        self._busy = False                    # 결제/대화상자 처리 중 → 중복/제스처 차단
        self._cursor_nx = 0.5                 # 제스처 커서의 최신 정규화 위치(x)
        self._cursor_ny = 0.5                 # 제스처 커서의 최신 정규화 위치(y)
        # 드웰(hover-to-select): 커서가 한 대상 위에 머문 시간을 재서 자동 선택
        self._dwell_target = None             # 현재 머무르는 대상 ("menu",item)/("checkout",None)
        self._dwell_start_ms = 0.0            # 머무름 시작 시각
        self._dwell_x = 0.5                   # 머무름 시작 시 커서 위치(이탈 판정용)
        self._dwell_y = 0.5
        self._active_voice_dialog = None      # 음성 주문 창 참조(열린 동안 제스처 라우팅)
        self._active_dialog = None            # 팝업/다이얼로그 참조(접근성 안내 등)
        # 팝업(안내창) 위에서도 에임 커서 + 드웰 클릭이 되도록 하는 상태값
        self._dialog_cursor = None            # 현재 팝업 위에 그리는 손 커서
        self._dialog_cursor_owner = None      # 그 커서가 속한 팝업(교체 감지용)
        self._dialog_dwell_target = None
        self._dialog_dwell_start_ms = 0.0
        self._dialog_dwell_x = 0.5
        self._dialog_dwell_y = 0.5
        self._intro_shown = False             # 현재 손님에게 접근성 안내를 이미 물었는지
        self._had_order = False               # 첫 주문을 마친 뒤로는 접근성 안내를 다시 묻지 않음
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
    # 접근성 안내(눈이 불편한 손님 → 고대비 + 음성 주문 바로가기)
    # ══════════════════════════════════════════
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
        """눈이 불편한지 음성으로 묻고, '네'면 고대비 화면 + 음성 주문으로 바로 진입합니다.

        · 음성(TTS)으로 질문을 읽어 줍니다.
        · 마이크로 '네/아니요'를 듣고(STT), '네'면 예 버튼을 자동으로 누릅니다.
        · 마이크가 없어도 화면의 예/아니요 버튼(또는 주먹 제스처)으로 응답할 수 있습니다.
        """
        self.speaker.say(self.tr.t("a11y_ask_tts"))

        # 세로 27인치 화면용 큰 안내창('네'·'아니요'를 화면 폭 가득 위아래로)
        box = ChoiceDialog("🦯 " + self.tr.t("a11y_ask_title"), self.tr.t("a11y_ask"),
                           self.tr.t("a11y_yes"), self.tr.t("a11y_no"),
                           style=self.styleSheet(), parent=self)
        yes_btn, no_btn = box.yes_btn, box.no_btn
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
            chose_yes = bool(box.exec())          # '네' → accept(1), '아니요'·Esc → reject(0)
        finally:
            self._active_dialog = None
            if self._intro_worker is not None and self._intro_worker.isRunning():
                self._intro_worker.wait(1500)
            self._intro_worker = None

        if chose_yes:
            self._start_voice_assist()

    def _start_voice_assist(self) -> None:
        """눈이 불편한 손님: 고대비 화면으로 바꾸고, 음성 주문 창을 마이크와 함께 엽니다.

        모드 전환 안내 음성은 생략합니다(음성 주문 안내와 겹쳐 마이크가 안내 소리를 듣지 않도록).
        """
        self._auto_mode_locked = True             # 연령 자동 전환이 고대비를 덮어쓰지 않게 고정
        self._set_mode(config.MODE_HIGH_CONTRAST)
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
                 "시각장애", "장애", "도와", "그렇", "좋아", "안 보", "안보",
                 "yes", "yeah", "yep", "yup", "correct", "sure", "okay", "ok",
                 "can't see", "cannot see",
                 "是", "对", "好", "嗯", "需要", "看不清")
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
        # 세로 1080×1920(LG 스탠바이미) 배치, 위에서 아래로:
        #   시연 도구(발표자용) → 머리글(가게 이름·상태·카메라) → 화면(환영/메뉴/완료)
        #   → 접근성 버튼(언어·고대비·소리·손동작: 휠체어·어린이도 손이 닿는 맨 아래)
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_demo_bar())     # 시연용 도구막대
        root.addWidget(self._build_header())

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_welcome_screen())   # 0
        self.stack.addWidget(self._build_menu_screen())      # 1
        self.stack.addWidget(self._build_done_screen())      # 2
        root.addWidget(self.stack, 1)

        root.addWidget(self._build_access_bar())

        # 오버레이: 제스처 커서 + 토스트(부모는 central)
        self.cursor = GestureCursor(central)
        self.toast = Toast(central)

    def _build_header(self) -> QWidget:
        """머리글: 가게 이름 + 인식 상태(모드·비전·손동작) + 카메라 미리보기.

        웹캠이 화면 위쪽에 달리므로 카메라 미리보기도 위쪽에 둡니다.
        글자 크기는 모드와 상관없이 고정 → 큰 글씨 모드에서도 화면 폭을 넘지 않음.
        """
        bar = QFrame()
        bar.setObjectName("Header")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(28, 12, 20, 12)
        lay.setSpacing(16)

        left = QVBoxLayout()
        left.setSpacing(6)
        self.logo = QLabel(f"🍔 {self.tr.t('store_name')}")
        self.logo.setObjectName("Logo")
        left.addWidget(self.logo)

        # 상태 줄(언어에 따라 길어지면 자동 줄바꿈)
        status_box = QWidget()
        sp = status_box.sizePolicy()
        sp.setHeightForWidth(True)
        sp.setVerticalPolicy(QSizePolicy.Policy.Minimum)
        status_box.setSizePolicy(sp)
        status_row = FlowLayout(status_box, spacing=18, alignment="left")
        self.mode_label = QLabel()
        self._vision_status_key = "vision_preparing"
        self.vision_label = QLabel(self.tr.t(self._vision_status_key))
        self.gesture_label = QLabel("✋ —")
        for lb in (self.mode_label, self.vision_label, self.gesture_label):
            lb.setObjectName("Status")
            status_row.addWidget(lb)
        left.addWidget(status_box)
        left.addStretch()
        lay.addLayout(left, 1)

        # 카메라 미리보기
        self.cam_view = QLabel()
        self.cam_view.setFixedSize(192, 144)
        self.cam_view.setStyleSheet("border:2px solid #2D6CDF; border-radius:10px;")
        self.cam_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cam_view.setText("CAM")
        lay.addWidget(self.cam_view)
        return bar

    def _build_access_bar(self) -> QWidget:
        """맨 아래 접근성 버튼 줄: 🌐 언어 · 👁 고대비 · 🔊 소리 안내 · ✋ 손동작.

        네 버튼이 화면 폭을 똑같이 나눠 쓰고(가로 크기 정책 Ignored), 글자 크기를 고정해
        어떤 모드·언어에서도 창이 1080px 보다 넓어지지 않습니다.
        """
        bar = QFrame()
        bar.setObjectName("AccessBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 12, 16, 14)
        lay.setSpacing(12)

        # 언어 전환 버튼(계획서 2.4 다국어: 한국어 → English → 中文 순환)
        self.lang_btn = QPushButton(LANG_NEXT_LABEL.get(self.tr.lang, "🌐 English"))
        self.lang_btn.clicked.connect(self._toggle_language)

        # 고대비 켜기/끄기(저시력자용). 누구나 바로 찾도록 맨 아래 고정 버튼으로 둠
        self.contrast_btn = QPushButton("👁 " + self.tr.t("contrast_mode"))
        self.contrast_btn.setCheckable(True)
        self.contrast_btn.setToolTip(self.tr.t("contrast_tooltip"))
        self.contrast_btn.clicked.connect(self._toggle_contrast)

        # 음성안내(TTS) 토글
        self.tts_btn = QPushButton()
        self.tts_btn.setCheckable(True)
        self.tts_btn.setChecked(config.TTS_ENABLED)
        self.tts_btn.clicked.connect(self._toggle_tts)

        # 손동작 제어 켜기/끄기(주문 중 원치 않는 손동작 오작동 방지)
        self.gesture_btn = QPushButton()
        self.gesture_btn.setCheckable(True)
        self.gesture_btn.setChecked(True)
        self.gesture_btn.setToolTip(self.tr.t("gesture_tooltip"))
        self.gesture_btn.clicked.connect(self._toggle_gesture)

        for b in (self.lang_btn, self.contrast_btn, self.tts_btn, self.gesture_btn):
            b.setObjectName("Access")
            b.setMinimumHeight(88)
            b.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            lay.addWidget(b, 1)
        self._refresh_access_texts()
        return bar

    def _refresh_access_texts(self) -> None:
        """접근성 버튼 글자(켜짐/꺼짐 그림 + 이름)를 현재 언어로 갱신."""
        self.lang_btn.setText(LANG_NEXT_LABEL.get(self.tr.lang, "🌐 English"))
        self.contrast_btn.setText("👁 " + self.tr.t("contrast_mode"))
        self.contrast_btn.setToolTip(self.tr.t("contrast_tooltip"))
        self.tts_btn.setText(("🔊 " if self.tts_btn.isChecked() else "🔈 ")
                             + self.tr.t("sound_btn"))
        self.gesture_btn.setText(("✋ " if self.gesture_btn.isChecked() else "🚫 ")
                                 + self.tr.t("gesture_btn"))
        self.gesture_btn.setToolTip(self.tr.t("gesture_tooltip"))

    def _build_demo_bar(self) -> QWidget:
        """카메라 없이도 모든 기능을 시연하기 위한 도구막대."""
        bar = QFrame()
        bar.setObjectName("StatusBar")
        # 발표자용 막대이므로 모드(글자 확대)와 상관없이 작게 유지 → 손님 화면 공간 확보
        bar.setStyleSheet("QPushButton, QLabel { font-size: 12pt; }"
                          "QPushButton { padding: 4px 10px; }")
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

    # ── 환영 화면 ──
    def _build_welcome_screen(self) -> QWidget:
        """세로 첫 화면: 큰 인사 → 인기 메뉴 그림 카드(2×2) → 손동작 안내 → 큰 시작 버튼.

        버튼은 화면 폭 가득, 손이 닿기 쉬운 아래쪽에 크게 둡니다(어린이·휠체어 이용자).
        """
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(48, 30, 48, 36)
        lay.setSpacing(18)
        lay.addStretch(2)

        self.welcome_title = QLabel(self.tr.t("welcome_title"))
        self.welcome_title.setObjectName("Hero")
        self.welcome_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.welcome_title.setWordWrap(True)
        self.welcome_sub = QLabel(self.tr.t("welcome_sub"))
        self.welcome_sub.setObjectName("SubTitle")
        self.welcome_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.welcome_sub.setWordWrap(True)
        lay.addWidget(self.welcome_title)
        lay.addWidget(self.welcome_sub)
        lay.addStretch(1)

        # 인기 메뉴 4종을 큰 그림 카드(2×2)로 미리 보여 줌(실버 모드 4종 전면 노출 컨셉)
        self.best_label = QLabel("🔥 " + self.tr.t("best_menu"))
        self.best_label.setObjectName("Section")
        lay.addWidget(self.best_label)
        best_grid = QGridLayout()
        best_grid.setSpacing(16)
        self.best_tiles: list[tuple[QLabel, QLabel, menu_data.MenuItem]] = []
        for i, m in enumerate(menu_data.best_sellers()[:4]):
            tile = QFrame()
            tile.setObjectName("Card")
            tl = QVBoxLayout(tile)
            tl.setContentsMargins(12, 18, 12, 18)
            tl.setSpacing(6)
            emoji = QLabel(m.emoji)
            emoji.setObjectName("TileEmoji")
            emoji.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name = QLabel()
            name.setObjectName("TileName")
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name.setWordWrap(True)
            price = QLabel()
            price.setObjectName("Price")
            price.setAlignment(Qt.AlignmentFlag.AlignCenter)
            for lb in (emoji, name, price):
                tl.addWidget(lb)
            self.best_tiles.append((name, price, m))
            best_grid.addWidget(tile, i // 2, i % 2)
        lay.addLayout(best_grid)

        self.welcome_hint = QLabel(self.tr.t("welcome_hint"))
        self.welcome_hint.setObjectName("Hint")
        self.welcome_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.welcome_hint.setWordWrap(True)
        lay.addWidget(self.welcome_hint)
        lay.addStretch(2)

        self.start_btn = QPushButton("🛎  " + self.tr.t("start_order"))
        self.start_btn.setObjectName("Primary")
        self.start_btn.setProperty("big", True)
        self.start_btn.setMinimumHeight(150)
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.clicked.connect(lambda: self._go_menu())

        # 환영 화면 음성 주문 버튼 — 첫 화면에서 바로 말로 주문 시작
        self.welcome_voice_btn = QPushButton("🎤  " + self.tr.t("voice_order"))
        self.welcome_voice_btn.setObjectName("Secondary")
        self.welcome_voice_btn.setProperty("big", True)
        self.welcome_voice_btn.setMinimumHeight(110)
        self.welcome_voice_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # 제스처/음성 사용자를 위해 열자마자 마이크를 자동으로 켠다(버튼을 누르지 않아도 말하면 입력됨).
        self.welcome_voice_btn.clicked.connect(lambda: self._open_voice_order(auto_listen=True))

        # 두 버튼을 화면 폭 가득 위아래로 → 큰 글씨 모드에서도 잘리지 않고 손 커서로도 맞히기 쉬움
        for b in (self.start_btn, self.welcome_voice_btn):
            b.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        lay.addWidget(self.start_btn)
        lay.addWidget(self.welcome_voice_btn)
        return w

    # ── 메뉴 화면 ──
    def _build_menu_screen(self) -> QWidget:
        """세로 메뉴 화면: 위에서부터 카테고리 탭 → 세트/음성 → 메뉴 그리드 → 장바구니."""
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(24, 16, 24, 16)
        outer.setSpacing(14)

        self.cat_bar = QHBoxLayout()
        self.cat_bar.setSpacing(12)
        self.cat_buttons: dict[str, QPushButton] = {}
        self.cat_group = QButtonGroup(self)
        for cat in menu_data.CATEGORY_ORDER:
            b = QPushButton()
            b.setCheckable(True)
            b.setObjectName("Ghost")
            b.setProperty("big", True)
            b.setMinimumHeight(90)
            b.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)   # 폭을 똑같이 3등분
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _, c=cat: self._select_category(c))
            self.cat_buttons[cat] = b
            self.cat_group.addButton(b)
            self.cat_bar.addWidget(b, 1)
        outer.addLayout(self.cat_bar)

        # 세트/단품 토글 + 음성 주문
        opt_row = QHBoxLayout()
        opt_row.setSpacing(12)
        self.set_toggle = QPushButton()
        self.set_toggle.setCheckable(True)
        self.set_toggle.setObjectName("Ghost")
        self.set_toggle.setMinimumHeight(80)
        self.set_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_toggle.clicked.connect(self._toggle_set)
        opt_row.addWidget(self.set_toggle, 1)

        self.voice_btn = QPushButton()
        self.voice_btn.setObjectName("Primary")
        self.voice_btn.setMinimumHeight(80)
        self.voice_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # 제스처/음성 사용자를 위해 열자마자 마이크를 자동으로 켠다.
        self.voice_btn.clicked.connect(lambda: self._open_voice_order(auto_listen=True))
        opt_row.addWidget(self.voice_btn, 1)
        for b in (self.set_toggle, self.voice_btn):
            b.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        outer.addLayout(opt_row)

        # 메뉴 그리드(스크롤 영역)
        self.menu_scroll = QScrollArea()
        self.menu_scroll.setWidgetResizable(True)
        self.menu_host = QWidget()
        self.menu_grid = QGridLayout(self.menu_host)
        self.menu_grid.setSpacing(14)
        self.menu_scroll.setWidget(self.menu_host)

        # 메뉴 영역을 넓게(위), 장바구니는 아래 패널로
        outer.addWidget(self.menu_scroll, 3)
        outer.addWidget(self._build_cart_panel(), 2)
        return w

    def _build_cart_panel(self) -> QWidget:
        """장바구니(화면 아래쪽 넓은 패널): 제목·합계 → 담은 목록 → 비우기 | 결제하기."""
        panel = QFrame()
        panel.setObjectName("Card")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(20, 16, 20, 18)
        lay.setSpacing(12)

        head = QHBoxLayout()
        self.cart_title = QLabel()
        self.cart_title.setObjectName("CartTitle")
        # 제목은 남는 폭만 쓰고(합계가 우선), 창 폭을 밀어내지 않음
        self.cart_title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.total_label = QLabel()
        self.total_label.setObjectName("CartTitle")
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignRight
                                      | Qt.AlignmentFlag.AlignVCenter)
        head.addWidget(self.cart_title, 1)
        head.addWidget(self.total_label)
        lay.addLayout(head)

        self.cart_scroll = QScrollArea()
        self.cart_scroll.setWidgetResizable(True)
        self.cart_host = QWidget()
        self.cart_list = QVBoxLayout(self.cart_host)
        self.cart_list.setSpacing(8)
        self.cart_list.addStretch()
        self.cart_scroll.setWidget(self.cart_host)
        lay.addWidget(self.cart_scroll, 1)

        self.clear_btn = QPushButton()
        self.clear_btn.setObjectName("Danger")
        self.clear_btn.setMinimumHeight(96)
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.clicked.connect(self._clear_cart)
        self.checkout_btn = QPushButton()
        self.checkout_btn.setObjectName("Primary")
        self.checkout_btn.setProperty("big", True)
        self.checkout_btn.setMinimumHeight(96)
        self.checkout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.checkout_btn.clicked.connect(self._checkout)
        # 결제 버튼을 더 넓게(2:1) → 손가락·손 멈춤(드웰) 대상이 크고, 비우기와 헷갈리지 않음
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        for b in (self.clear_btn, self.checkout_btn):
            b.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        btn_row.addWidget(self.clear_btn, 1)
        btn_row.addWidget(self.checkout_btn, 2)
        lay.addLayout(btn_row)
        return panel

    # ── 결제 완료 화면 ──
    def _build_done_screen(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(48, 40, 48, 40)
        lay.setSpacing(20)
        lay.addStretch(1)

        self.done_emoji = QLabel("✅")
        self.done_emoji.setStyleSheet("font-size:150pt;")
        self.done_emoji.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.done_title = QLabel()
        self.done_title.setObjectName("Hero")
        self.done_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.done_title.setWordWrap(True)
        # 주문번호: 작은 제목 + 아주 큰 숫자(멀리서도 번호를 읽고 기억하기 쉽게)
        self.done_number_caption = QLabel()
        self.done_number_caption.setObjectName("SubTitle")
        self.done_number_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.done_number = QLabel()
        self.done_number.setObjectName("OrderNo")
        self.done_number.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.done_emoji)
        lay.addWidget(self.done_title)
        lay.addSpacing(30)
        lay.addWidget(self.done_number_caption)
        lay.addWidget(self.done_number)
        lay.addStretch(1)
        return w

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
        # 어떤 경로(접근성 버튼·시연 도구·접근성 안내·연령 자동)로 바뀌어도 버튼 상태를 화면과 맞춤
        self.contrast_btn.setChecked(self.mode == config.MODE_HIGH_CONTRAST)
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
        self._refresh_access_texts()
        self.best_label.setText("🔥 " + self.tr.t("best_menu"))
        won = self.tr.t("won")
        for name, price, m in self.best_tiles:
            name.setText(m.name(self.tr.lang))
            price.setText(f"{m.price:,}{won}")
        self.welcome_hint.setText(self.tr.t("welcome_hint"))
        self._set_vision_status(self._vision_status_key)
        self._refresh_demo_bar_texts()
        labels = menu_data.CATEGORY_LABELS[self.tr.lang]
        cat_emoji = {menu_data.CATEGORY_BURGER: "🍔", menu_data.CATEGORY_SIDE: "🍟",
                     menu_data.CATEGORY_DRINK: "🥤"}
        for cat, b in self.cat_buttons.items():
            b.setText(f"{cat_emoji.get(cat, '')} {labels[cat]}".strip())
        self._update_set_toggle_text()
        self._refresh_menu_grid()
        self._refresh_cart()

    def _toggle_language(self) -> None:
        self.tr.set_lang(next_lang(self.tr.lang))
        self._apply_theme()

    def _toggle_tts(self) -> None:
        on = self.tts_btn.isChecked()
        self.speaker.toggle(on)
        self._refresh_access_texts()

    def _toggle_gesture(self) -> None:
        """손동작 제어를 켜고 끕니다(원치 않는 손동작 오작동 방지)."""
        self._gesture_enabled = self.gesture_btn.isChecked()
        self._refresh_access_texts()
        if not self._gesture_enabled:
            self.cursor.hide()
            self.gesture_label.setText("✋ " + self.tr.t("gesture_off"))
        self._show_toast(self.tr.t("gesture_on_toast") if self._gesture_enabled
                         else self.tr.t("gesture_off_toast"))

    def _manual_set_mode(self, mode: str) -> None:
        """시연 버튼으로 모드를 직접 바꿉니다(자동 전환 잠금)."""
        self._auto_mode_locked = True
        self._set_mode(mode, announce=True)

    def _toggle_contrast(self) -> None:
        """아래쪽 고대비 버튼: 켜면 고대비 화면, 끄면 직전 화면으로 돌아갑니다."""
        if self.contrast_btn.isChecked():
            self._manual_set_mode(config.MODE_HIGH_CONTRAST)
        else:
            self._auto_mode_locked = True     # 손님이 직접 고른 화면을 연령 자동 전환이 바꾸지 않게
            self._set_mode(self._mode_before_contrast, announce=True)

    def _set_mode(self, mode: str, announce: bool = False) -> None:
        if mode == self.mode:
            return
        if mode == config.MODE_HIGH_CONTRAST:
            self._mode_before_contrast = self.mode
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
            cols = 3          # 세로 화면 폭(1080)에 카드 3장
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
            empty.setWordWrap(True)
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
                               speaker=self.speaker, auto_listen=auto_listen,
                               theme=theme_mod.get_theme(self.mode))
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
        spoken: list[str] = []  # 담은 메뉴를 소리로 읽어 줄 문구
        for intent in result.intents:
            added += self._apply_intent(intent, spoken)
            if intent.action in ("clear", "checkout"):
                handled = True
        self._refresh_cart()
        # 눈이 불편한 손님도 결과를 알 수 있도록 화면 알림과 함께 소리로 읽어 줍니다.
        if added:
            self._show_toast(f"🎤 {self.tr.t('engine_smart')}: "
                             f"{self.tr.t('voice_added').format(n=added)}")
            self.speaker.say(self.tr.t("voice_result_tts").format(
                items=", ".join(spoken), total=f"{self.cart.total():,}"))
        elif any(i.action == "clear" for i in result.intents):
            self.speaker.say(self.tr.t("cleared_tts"))
        elif not handled:
            self._show_toast("🤔 " + self.tr.t("not_understood"))
            self.speaker.say(self.tr.t("not_understood"))

    def _apply_intent(self, intent: OrderIntent, spoken: list[str] | None = None) -> int:
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
        if spoken is not None:
            name = item.name(self.tr.lang)
            if is_set:
                name += " " + self.tr.t("set_word")
            spoken.append(self.tr.t("voice_item_tts").format(name=name, qty=intent.qty))
        return intent.qty

    # ══════════════════════════════════════════
    # 결제
    # ══════════════════════════════════════════
    def _checkout(self) -> None:
        if self.cart.is_empty():
            self._show_toast("🧺 " + self.tr.t("cart_empty"))
            return
        if self._busy:            # 이미 결제 처리 중이면 중복 실행 차단(대화상자 2개 방지)
            return
        self._busy = True
        self._had_order = True    # 첫 주문 완료 → 이후로는 접근성 안내를 다시 묻지 않음
        # 판매 통계 저장(계획서 6장 빅데이터)
        self.db.record_order(self.cart.to_records(), self.cart.total())

        self._order_counter += 1
        self.done_title.setText("🎉 " + self.tr.t("thank_you"))
        self.done_number_caption.setText(self.tr.t("order_number"))
        self.done_number.setText(str(self._order_counter))
        self.speaker.say(self.tr.t("thank_you"))
        self.stack.setCurrentIndex(SCREEN_DONE)
        QTimer.singleShot(3500, self._reset_session)

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

    def _on_face_present(self, present: bool) -> None:
        if present:
            # 사람이 실제로 감지됐을 때만, 아직 안 물었고 첫 주문 전이면 접근성 안내를 띄웁니다.
            if (config.ACCESSIBILITY_INTRO_ENABLED
                    and not self._intro_shown and not self._had_order):
                self._intro_shown = True
                QTimer.singleShot(900, self._maybe_intro_accessibility)
            return
        # 손님이 떠나면(얼굴 사라짐) 다음 손님을 준비합니다.
        if not self._busy:
            self._age_votes.clear()       # 연령 투표함 초기화
            if not self._had_order:
                self._intro_shown = False  # 새 손님에게는 다시 물을 수 있도록 재무장

    def _on_gesture(self, name: str, x: float, y: float) -> None:
        # 손동작이 꺼져 있으면 모두 무시
        if not self._gesture_enabled:
            self.cursor.hide()
            self._reset_dwell()
            self.gesture_label.setText("✋ " + self.tr.t("gesture_off"))
            return
        # 음성 주문 창이 열려 있으면 제스처를 다이얼로그로 라우팅(배경 오작동 방지)
        if self._active_voice_dialog is not None:
            self.cursor.hide()                        # 메인 커서 숨김(창이 자체 커서 사용)
            # 에임: 손이 편하게 있으면(가리키기/펼침/V/대기) 창 안에서 커서 이동 + 드웰
            if name in ("point", "open_palm", "idle", "sign_two"):
                dx = x - self._cursor_nx
                dy = y - self._cursor_ny
                dist = (dx * dx + dy * dy) ** 0.5
                if dist > config.CURSOR_MAX_STEP:      # 순간이동 방지(한 프레임 이동 제한)
                    f = config.CURSOR_MAX_STEP / dist
                    x = self._cursor_nx + dx * f
                    y = self._cursor_ny + dy * f
                self._cursor_nx, self._cursor_ny = x, y
                self._active_voice_dialog.receive_aim(x, y)
                return
            if name in ("fist_hold", "sign_hold"):
                return                                # 집는 중 → 드웰 진행 유지
            if name in ("swipe_left", "swipe_right", "fist", "sign_yes"):
                now = time.time() * 1000
                if now - self._last_gesture_action_ms < self._gesture_cooldown_ms(name):
                    return
                self._last_gesture_action_ms = now
                self._active_voice_dialog.receive_gesture(name)
            return
        # 팝업/다이얼로그이 열려 있으면 제스처를 팝업으로 라우팅
        if self._active_dialog is not None:
            self.cursor.hide()                        # 메인 커서 숨김(팝업이 자체 커서 사용)
            # 에임: 손이 편하게 있으면 팝업 안에서 커서 이동 + 드웰(버튼 위 머무르면 클릭)
            if name in ("point", "open_palm", "idle", "sign_two"):
                dx = x - self._cursor_nx
                dy = y - self._cursor_ny
                dist = (dx * dx + dy * dy) ** 0.5
                if dist > config.CURSOR_MAX_STEP:
                    f = config.CURSOR_MAX_STEP / dist
                    x = self._cursor_nx + dx * f
                    y = self._cursor_ny + dy * f
                self._cursor_nx, self._cursor_ny = x, y
                self._update_dialog_dwell(x, y)
                return
            if name in ("fist_hold", "sign_hold"):
                return                                # 집는 중 → 드웰 진행 유지
            if name in ("fist", "sign_yes", "swipe_left", "swipe_right"):
                now = time.time() * 1000
                if now - self._last_gesture_action_ms < self._gesture_cooldown_ms(name):
                    return
                self._last_gesture_action_ms = now
                self._handle_dialog_gesture(name)
            return
        # 결제 처리 중이면 제스처 차단
        if self._busy:
            self.cursor.hide()
            self._reset_dwell()
            return
        self.gesture_label.setText(f"✋ {name}")
        # ── 에임(aim): 손이 편하게 있으면(가리키기/펼침/V/대기) 커서를 계속 따라가게 한다.
        #    포즈 전환에 의존하지 않아 안정적이며, 위에서 손바닥 중심을 커서로 쓴다.
        if name in ("point", "open_palm", "idle", "sign_two"):
            # 커서 순간이동 방지: 이전 위치 대비 한 프레임 이동량을 제한(클램프).
            dx = x - self._cursor_nx
            dy = y - self._cursor_ny
            dist = (dx * dx + dy * dy) ** 0.5
            if dist > config.CURSOR_MAX_STEP:
                f = config.CURSOR_MAX_STEP / dist
                x = self._cursor_nx + dx * f
                y = self._cursor_ny + dy * f
            self._cursor_nx, self._cursor_ny = x, y   # 커서 위치 기억(핀치 담기에 사용)
            central = self.centralWidget()
            self.cursor.move_norm(central.width(), central.height(), x, y)
            self._update_dwell(x, y)                  # 드웰(머무름) 선택 진행
            return
        if name in ("fist_hold", "sign_hold"):
            return                                    # 쥐는/집는 중 → 커서·드웰 유지
        # 실제 '동작' 제스처만, 일정 간격(쿨다운)을 두고 한 번씩 실행 → 연속 오작동 차단
        if name not in ("swipe_left", "swipe_right", "fist", "sign_yes"):
            return
        self._reset_dwell()                           # 동작이 실행되면 드웰 리셋
        now = time.time() * 1000
        if now - self._last_gesture_action_ms < self._gesture_cooldown_ms(name):
            return
        self._last_gesture_action_ms = now
        self._handle_gesture_action(name)

    def _gesture_cooldown_ms(self, name: str) -> float:
        """동작별 차등 쿨다운: 담기는 짧게(연속 담기), 스와이프/결제는 넉넉히."""
        if name == "fist":
            return config.GRAB_COOLDOWN_MS
        if name in ("swipe_left", "swipe_right"):
            return config.SWIPE_COOLDOWN_MS
        return config.GESTURE_ACTION_COOLDOWN_MS

    # ── 드웰(hover-to-select): 커서가 한 대상 위에 머물면 자동 선택 ──
    def _update_dwell(self, nx: float, ny: float) -> None:
        """커서가 대상 위에 머무는 시간을 재서, 임계 시간이 지나면 자동 선택합니다."""
        if not config.DWELL_ENABLED or self._busy:
            self._reset_dwell()
            return
        if self.stack.currentIndex() not in (SCREEN_WELCOME, SCREEN_MENU):
            self._reset_dwell()
            return
        target = self._dwell_target_under_cursor()
        if target is None:
            self._reset_dwell()
            return
        now = time.time() * 1000
        moved = ((nx - self._dwell_x) ** 2 + (ny - self._dwell_y) ** 2) ** 0.5
        # 대상이 바뀌었거나 커서가 많이 움직이면 타이머를 새로 시작
        if target != self._dwell_target or moved > config.DWELL_MOVE_TOLERANCE:
            self._dwell_target = target
            self._dwell_start_ms = now
            self._dwell_x, self._dwell_y = nx, ny
            self.cursor.set_progress(0.0)
            return
        elapsed = now - self._dwell_start_ms
        self.cursor.set_progress(elapsed / config.DWELL_SELECT_MS)
        if elapsed >= config.DWELL_SELECT_MS:
            if now - self._last_gesture_action_ms < config.GRAB_COOLDOWN_MS:
                return
            self._last_gesture_action_ms = now
            self._activate_dwell(target)
            self._reset_dwell()

    def _reset_dwell(self) -> None:
        if self._dwell_target is not None:
            self._dwell_target = None
        self.cursor.set_progress(0.0)

    def _dwell_target_under_cursor(self):
        """커서 아래의 드웰 대상.

        · 환영 화면: 주문 시작 버튼 · 음성 주문 버튼
        · 메뉴 화면: 메뉴 카드 · 음성 주문 버튼 · (장바구니가 찼을 때) 결제 버튼
        """
        if self.stack.currentIndex() == SCREEN_WELCOME:
            if self._cursor_over_widget(self.start_btn):
                return ("start", None)
            if self._cursor_over_widget(self.welcome_voice_btn):
                return ("voice", None)
            return None
        item = self._menu_item_under_cursor()
        if item is not None:
            return ("menu", item)
        if self._cursor_over_widget(self.voice_btn):
            return ("voice", None)
        if not self.cart.is_empty() and self._cursor_over_widget(self.checkout_btn):
            return ("checkout", None)
        return None

    def _cursor_over_widget(self, w) -> bool:
        """커서 위치가 특정 위젯의 영역 안에 있는지 검사."""
        if w is None or not w.isVisible():
            return False
        central = self.centralWidget()
        if central is None:
            return False
        px = int(self._cursor_nx * central.width())
        py = int(self._cursor_ny * central.height())
        origin = w.mapTo(central, w.rect().topLeft())
        return w.rect().translated(origin).contains(px, py)

    def _activate_dwell(self, target) -> None:
        kind, payload = target
        if kind == "start":
            self._go_menu()
        elif kind == "menu":
            self._add_to_cart(payload)            # 자체 토스트/음성 안내 포함
        elif kind == "voice":
            self._open_voice_order(auto_listen=True)   # 음성 주문 창 열기(마이크 자동 시작)
        elif kind == "checkout":
            self._checkout()
        self._reset_idle()

    # ── 팝업(안내창) 위 에임 커서 + 드웰(머무름) 클릭 ──
    def _ensure_dialog_cursor(self):
        """현재 팝업 위에 드웰용 손 커서를 준비합니다(팝업이 바뀌면 새로 만듦)."""
        dlg = self._active_dialog
        if dlg is None:
            return None
        # 파이썬 참조로만 비교(삭제된 C++ 객체 접근 방지)
        if self._dialog_cursor is None or self._dialog_cursor_owner is not dlg:
            self._dialog_cursor = GestureCursor(dlg)
            self._dialog_cursor_owner = dlg
            self._dialog_dwell_target = None
        return self._dialog_cursor

    def _update_dialog_dwell(self, nx: float, ny: float) -> None:
        """커서를 팝업 안에서 옮기고, 버튼 위에 DWELL_SELECT_MS 머물면 그 버튼을 누릅니다."""
        dlg = self._active_dialog
        if dlg is None or not config.DWELL_ENABLED:
            return
        cur = self._ensure_dialog_cursor()
        if cur is None:
            return
        cur.move_norm(dlg.width(), dlg.height(), nx, ny)
        target = self._dialog_button_under_cursor(nx, ny)
        if target is None:
            self._dialog_dwell_target = None
            cur.set_progress(0.0)
            return
        now = time.time() * 1000
        moved = ((nx - self._dialog_dwell_x) ** 2 + (ny - self._dialog_dwell_y) ** 2) ** 0.5
        if target is not self._dialog_dwell_target or moved > config.DWELL_MOVE_TOLERANCE:
            self._dialog_dwell_target = target
            self._dialog_dwell_start_ms = now
            self._dialog_dwell_x, self._dialog_dwell_y = nx, ny
            cur.set_progress(0.0)
            return
        elapsed = now - self._dialog_dwell_start_ms
        cur.set_progress(elapsed / config.DWELL_SELECT_MS)
        if elapsed >= config.DWELL_SELECT_MS:
            if now - self._last_gesture_action_ms < config.GRAB_COOLDOWN_MS:
                return
            self._last_gesture_action_ms = now
            self._dialog_dwell_target = None
            cur.set_progress(0.0)
            if target.isEnabled():
                target.click()

    def _dialog_button_under_cursor(self, nx: float, ny: float):
        """팝업 커서(정규화 좌표) 아래에 있는, 눌러지는 버튼을 찾습니다."""
        dlg = self._active_dialog
        if dlg is None:
            return None
        px = int(nx * dlg.width())
        py = int(ny * dlg.height())
        w = dlg.childAt(px, py)
        while w is not None:
            if isinstance(w, QPushButton) and w.isEnabled():
                return w
            w = w.parentWidget()
        return None

    def _handle_dialog_gesture(self, name: str) -> None:
        """팝업에서 주먹 쥐기 / 엄지척 → '네' 버튼 클릭(스와이프는 무시)"""
        if self._active_dialog is None:
            return
        if name in ("fist", "sign_yes"):
            yes_btn = getattr(self._active_dialog, "yes_btn", None)
            if yes_btn is not None:
                yes_btn.click()

    def _handle_gesture_action(self, name: str) -> None:
        # 엄지척은 '쥐기'와 똑같이 처리합니다. 엄지 인식은 흔들리기 쉬워서
        # 실수로 결제되지 않도록 결제는 '결제 버튼 위 드웰'·터치·음성으로만 합니다.
        if name == "sign_yes":
            name = "fist"
        if self.stack.currentIndex() == SCREEN_WELCOME:
            # 집기는 커서가 가리키는 버튼만 누릅니다. 지나가는 손짓으로 넘어가 버리면
            # 눈이 불편한 손님에게 묻는 접근성 안내를 건너뛰게 되기 때문입니다.
            if name == "fist" and not self.cursor.isHidden():
                if self._cursor_over_widget(self.start_btn):
                    self._go_menu()
                elif self._cursor_over_widget(self.welcome_voice_btn):
                    self._open_voice_order(auto_listen=True)
            return
        if self.stack.currentIndex() != SCREEN_MENU:
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
        """카메라 미리보기를 머리글(오른쪽 위)에 표시."""
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
