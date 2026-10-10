"""
ui/voice_dialog.py — 음성 주문 입력 창 (계획서 2.4)
================================================
마이크로 말하거나(STT) 텍스트로 주문 문장을 입력받아
오프라인 규칙 기반 NLU 로 분석하는 대화창입니다.

· 🎙 말하기 → 마이크로 말하면 글자로 받아 적어 줍니다(Google STT).
· 마이크 듣기는 별도 스레드(QThread)에서 처리해 화면이 멈추지 않습니다.
· 예시 문장 버튼을 누르면 자동으로 채워져 시연이 편합니다.
· 마이크/인터넷이 없으면 버튼이 비활성화되고 직접 입력으로 안내합니다.
· 안내·인식 결과·실패 이유를 모두 소리(TTS)로도 알려 줍니다(눈이 불편한 손님).
"""
from __future__ import annotations

import importlib.util
import re
import threading
import time

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QVBoxLayout)

import config
from core.i18n import Translator
from ui.widgets import GestureCursor

# STT(음성인식)에 쓸 Google 언어 코드(언어별)
STT_LANG_CODE = {"ko": "ko-KR", "en": "en-US", "zh": "zh-CN"}


def speech_available() -> bool:
    """speech_recognition 과 pyaudio 가 모두 설치돼 있는지 확인."""
    return (importlib.util.find_spec("speech_recognition") is not None
            and importlib.util.find_spec("pyaudio") is not None)


def find_mic_index(name: str) -> int | None:
    """이름(일부)이 맞는 마이크의 장치 번호. 비었거나 못 찾으면 None(= Windows 기본 마이크)."""
    if not name:
        return None
    try:
        import speech_recognition as sr
        for i, dev in enumerate(sr.Microphone.list_microphone_names()):
            if dev and name.lower() in dev.lower():
                return i
    except Exception:
        pass
    print(f"[마이크] '{name}' 마이크를 찾지 못해 Windows 기본 마이크를 사용합니다.", flush=True)
    return None


def order_understood(text: str) -> bool:
    """문장이 메뉴 담기나 결제·비우기 같은 주문으로 이해되는지."""
    from core.nlu import parse_order
    result = parse_order(text)
    return any(i.item_id or i.action in ("clear", "checkout") for i in result.intents)


# 영어를 한국어 인식기로 들으면 나오는 한글 발음 표기(예: '투 치즈버거 플리즈')
_HANGUL_ENGLISH = ("플리즈", "앤드", " 앤 ", "투 ", "쓰리 ", "파이브", "위드", "아이 원트",
                   "기브 미", "프렌치", "프라이즈", "라지 ", " 콕", "버거스", "셋 ", "오더")


def transcript_score(lang: str, text: str, confidence: float, ui_lang: str) -> float:
    """여러 언어 인식 결과 중 고를 점수: 인식기 신뢰도 + 주문으로 이해됨 + (동점이면) 화면 언어."""
    score = confidence
    if order_understood(text):
        score += 0.35
    if lang == ui_lang:
        score += 0.05
    if lang == "ko" and looks_english_in_hangul(text):
        score -= 0.4                         # 영어를 한글 발음으로 받아 적은 결과는 감점
    # 언어와 글자가 맞지 않으면 감점(예: 영어 말을 중국어 인식기가 'QQQ'로 받아 적음, 신뢰도는 높게 나옴)
    script_ok = {"ko": r"[가-힣]", "zh": r"[一-鿿]", "en": r"[A-Za-z]"}.get(lang)
    if script_ok and not re.search(script_ok, text):
        score -= 0.5
    return score


def looks_english_in_hangul(text: str) -> bool:
    """한국어 인식 결과가 영어를 한글로 받아 적은 것처럼 보이는지(표기 2개 이상)."""
    padded = f" {text} "
    return sum(1 for w in _HANGUL_ENGLISH if w in padded) >= 2


def run_when_quiet(speaker, callback, min_delay_ms: int = 0, max_wait_ms: int = 20000) -> None:
    """안내 음성(TTS)이 다 끝나고 잠깐 쉰 뒤에 callback 을 부릅니다.

    안내가 나오는 동안 마이크를 켜면 키오스크 자신의 목소리를 '주변 소음'으로 재서
    듣기 기준이 너무 높아지고, 손님의 짧은 대답('네')을 놓치게 됩니다.
    """
    start = time.time() * 1000

    def check() -> None:
        busy = speaker is not None and speaker.is_speaking()
        if busy and time.time() * 1000 - start < max_wait_ms:
            QTimer.singleShot(150, check)
            return
        QTimer.singleShot(config.TTS_QUIET_GAP_MS, callback)

    QTimer.singleShot(min_delay_ms, check)


class SpeechWorker(QThread):
    """마이크로 듣고 Google STT 로 글자를 받아오는 백그라운드 스레드.

    short_answer=True 는 '네/아니요' 같은 한두 마디 대답용입니다. 짧은 말은 인식기가
    한 가지 답만 내면 놓치기 쉬워서, 인식 후보를 모두 받아 ' / ' 로 이어서 돌려줍니다.
    """

    # 단계별 상태 메시지 / 성공 결과 / 실패 사유
    status = pyqtSignal(str)
    recognized = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, lang: str, parent=None, short_answer: bool = False):
        super().__init__(parent)
        self.lang = lang
        self.tr = Translator(lang)
        self.short_answer = short_answer

    def run(self) -> None:
        try:
            import speech_recognition as sr
        except Exception as e:
            self.failed.emit(f"{self.tr.t('mic_lib_missing')}: {e}")
            return
        try:
            recognizer = sr.Recognizer()
            if self.short_answer:
                recognizer.pause_threshold = 0.5      # 짧은 대답 뒤 바로 끊어서 인식
                recognizer.non_speaking_duration = 0.3
            with sr.Microphone(device_index=find_mic_index(config.MIC_NAME)) as source:
                # 주변 소음 수준을 잠깐 측정해 인식률을 높입니다(노이즈 보정).
                self.status.emit(self.tr.t("calibrating"))
                recognizer.adjust_for_ambient_noise(source, duration=0.6)
                self.status.emit(self.tr.t("speak_now"))
                audio = recognizer.listen(source, timeout=6,
                                          phrase_time_limit=4 if self.short_answer else 10)
        except Exception:
            # timeout 등: 사용자가 말을 안 했거나 마이크 접근 실패
            self.failed.emit(self.tr.t("no_speech"))
            return

        self.status.emit(self.tr.t("recognizing"))
        if not self.short_answer:
            self._recognize_order(sr, recognizer, audio)
            return
        try:
            lang_code = STT_LANG_CODE.get(self.lang, "en-US")
            result = recognizer.recognize_google(audio, language=lang_code, show_all=True)
            alts = result.get("alternative", []) if isinstance(result, dict) else []
            text = " / ".join(a.get("transcript", "") for a in alts if a.get("transcript"))
            if text and text.strip():
                self.recognized.emit(text.strip())
            else:
                self.failed.emit(self.tr.t("cannot_understand"))
        except sr.UnknownValueError:
            self.failed.emit(self.tr.t("cannot_understand_clear"))
        except sr.RequestError:
            # 인터넷 연결이 없을 때(Google STT 는 온라인 필요)
            self.failed.emit(self.tr.t("internet_required"))
        except Exception as e:
            self.failed.emit(f"{self.tr.t('error_label')}: {e}")

    def _recognize_order(self, sr, recognizer, audio) -> None:
        """주문 문장 인식: 한국어·영어·중국어 인식기에 '동시에' 보내고 가장 믿을 만한 결과를 씀.

        한 언어 인식기는 다른 언어 말을 억지로 자기 언어로 받아 적습니다(영어를 한국어 인식기로
        들으면 '투 치즈버거 플리즈'). 세 언어로 동시에 인식한 뒤, 인식기가 매긴 신뢰도와
        '주문으로 이해되는지'를 함께 보고 고릅니다. 동시에 보내므로 기다리는 시간은 거의 같습니다.
        """
        langs = [self.lang]
        if config.VOICE_MULTI_LANG:
            langs += [lg for lg in ("ko", "en", "zh") if lg != self.lang]
        results: dict[str, tuple[str, float] | None] = {}
        net_error = []

        def work(lg: str) -> None:
            try:
                res = recognizer.recognize_google(audio, language=STT_LANG_CODE.get(lg, "en-US"),
                                                  show_all=True)
            except sr.RequestError:
                net_error.append(lg)
                return
            except Exception:
                results[lg] = None
                return
            alts = res.get("alternative", []) if isinstance(res, dict) else []
            text = (alts[0].get("transcript", "") if alts else "").strip()
            conf = float(alts[0].get("confidence", 0.5)) if alts else 0.0
            results[lg] = (text, conf) if text else None

        threads = [threading.Thread(target=work, args=(lg,), daemon=True) for lg in langs]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        candidates = [(lg, *results[lg]) for lg in langs if results.get(lg)]
        if not candidates:
            self.failed.emit(self.tr.t("internet_required") if net_error
                             else self.tr.t("cannot_understand_clear"))
            return
        best = max(candidates, key=lambda c: transcript_score(c[0], c[1], c[2], self.lang))
        self.recognized.emit(best[1])


class VoiceOrderDialog(QDialog):
    """자연어 주문 문장을 입력받는 창."""

    EXAMPLES_KO = [
        "불고기버거 세트 하나 주세요, 콜라는 라지로 바꿔주세요",
        "더블 치즈버거 두 개랑 감자튀김 주세요",
        "새우버거 세트랑 사이드는 치즈스틱으로 바꿔주세요",
        "한우버거 하나랑 오렌지주스 주세요",
    ]
    EXAMPLES_EN = [
        "One bulgogi burger set, change the cola to large",
        "Two double cheeseburgers and french fries please",
        "A shrimp burger set with cheese stick instead of fries",
    ]
    EXAMPLES_ZH = [
        "来一份烤肉汉堡套餐，可乐换成大杯",
        "两个双层芝士汉堡和薯条",
        "一份鲜虾汉堡套餐，配菜换成芝士棒",
    ]

    def __init__(self, lang: str, hint: str, listening_text: str, parent=None,
                 speaker=None, auto_listen: bool = False, theme=None,
                 on_text=None, can_checkout=None):
        super().__init__(parent)
        self.lang = lang
        self.tr = Translator(lang)
        self.speaker = speaker            # 음성 안내(TTS) 엔진(없으면 조용히 무시)
        self._worker: SpeechWorker | None = None
        # 대화식 모드: on_text(문장) 가 있으면 알아들은 말을 창 안에서 바로 처리하고 계속 듣습니다.
        self._on_text = on_text
        self._can_checkout = can_checkout
        self._auto = auto_listen          # 자동으로 계속 듣기(시각장애인 흐름·음성 주문 버튼)
        self._fails = 0                   # 연속으로 못 알아들은 횟수(자동 재시도 제한)
        self.checkout_requested = False   # 창을 닫은 뒤 바로 결제할지
        # 고대비 등 현재 화면 테마의 색을 따라야 저시력자도 안내 글씨를 읽을 수 있음
        sub_color = theme.sub_text if theme else "#5C6B82"
        accent = theme.primary if theme else "#2D6CDF"
        self.setWindowTitle("🎤 " + self.tr.t("voice_title"))
        # 세로 27인치 화면(폭 1080)에 맞춘 넓은 창. 큰 글씨 모드에서도 화면 밖으로 넘지 않게 상한을 둠
        max_w = 1040
        if parent is not None and parent.width() > 0:   # 메인 화면보다 넓어지지 않게
            max_w = min(max_w, parent.width() - 40)
        self.setMinimumWidth(min(900, max_w))
        self.setMaximumWidth(max_w)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(16)

        title = QLabel("🎤 " + self.tr.t("voice_natural"))
        title.setStyleSheet("font-size:26pt; font-weight:800;")
        title.setWordWrap(True)
        lay.addWidget(title)

        sub = QLabel(hint)
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color:{sub_color};")
        lay.addWidget(sub)

        self.input = QLineEdit()
        self.input.setPlaceholderText(listening_text)
        self.input.setMinimumHeight(76)
        self.input.setStyleSheet("font-size:20pt; padding:12px; border-radius:12px;"
                                 f"border:2px solid {accent};")
        self.input.returnPressed.connect(self._submit_input)
        lay.addWidget(self.input)

        # 마이크 상태 안내 줄
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(f"color:{accent}; font-weight:700;")
        lay.addWidget(self.status_label)

        # 예시 문장 버튼들(시연 편의) — 긴 문장이 창 폭을 넘지 않도록 글자 크기 고정
        ex_label = QLabel(self.tr.t("examples_label"))
        ex_label.setStyleSheet(f"color:{sub_color}; font-weight:700;")
        lay.addWidget(ex_label)
        examples = {"ko": self.EXAMPLES_KO, "en": self.EXAMPLES_EN,
                    "zh": self.EXAMPLES_ZH}.get(lang, self.EXAMPLES_EN)
        for ex in examples:
            b = QPushButton(ex)
            b.setObjectName("Ghost")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setMinimumHeight(64)
            b.setStyleSheet("text-align:left; padding:10px 16px; font-size:18pt;")
            b.clicked.connect(lambda _, t=ex: self.input.setText(t))
            lay.addWidget(b)

        # 실제 마이크 버튼 + 확인/취소
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        self.mic_btn = QPushButton("🎙 " + self.tr.t("speak"))
        self.mic_btn.setObjectName("Ghost")
        self.mic_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mic_btn.clicked.connect(self._start_speech)
        # 라이브러리가 없으면 마이크 버튼을 비활성화하고 이유를 안내합니다.
        if not speech_available():
            self.mic_btn.setEnabled(False)
            self.mic_btn.setText("🎙 " + self.tr.t("mic_na"))
            self.status_label.setText(self.tr.t("mic_hint"))
        cancel = QPushButton(self.tr.t("cancel"))
        cancel.clicked.connect(self.reject)
        ok = QPushButton(self.tr.t("analyze"))
        ok.setObjectName("Primary")
        ok.clicked.connect(self._submit_input)
        for b in (self.mic_btn, cancel, ok):
            b.setMinimumHeight(84)
        btn_row.addWidget(self.mic_btn)
        btn_row.addStretch()
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok)
        lay.addLayout(btn_row)
        # 음성으로 담은 뒤 창을 닫지 않고 바로 결제할 수 있는 큰 버튼
        self.pay_btn = QPushButton("💳 " + self.tr.t("checkout"))
        self.pay_btn.setObjectName("Primary")
        self.pay_btn.setMinimumHeight(84)
        self.pay_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pay_btn.clicked.connect(self._request_checkout)
        self.pay_btn.setVisible(on_text is not None)
        lay.addWidget(self.pay_btn)
        self._refresh_pay_btn()

        # 손동작 힌트(카메라 제스처로 다이얼로그를 조작할 수 있음을 안내)
        self.gesture_hint_label = QLabel(self.tr.t("voice_gesture_hint"))
        self.gesture_hint_label.setStyleSheet(f"color:{sub_color}; font-size:14pt;")
        self.gesture_hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.gesture_hint_label.setWordWrap(True)
        lay.addWidget(self.gesture_hint_label)

        # ── 제스처 에임 커서 + 드웰(머무름) 클릭 ─────────────────
        # 메뉴 화면처럼 손을 움직여 커서를 옮기고, 버튼 위에 잠시 멈추면(드웰)
        # 자동으로 눌립니다. 마이크(다시 말하기) 버튼도 손으로 다시 켤 수 있습니다.
        self._dwell_target: QPushButton | None = None
        self._dwell_start_ms = 0.0
        self._dwell_x = 0.5
        self._dwell_y = 0.5
        self._last_dwell_ms = 0.0
        self._aim: tuple[float, float] | None = None   # 손 커서의 현재 위치(집게 손 클릭용)
        self.cursor = GestureCursor(self)   # 창 위에 그려지는 손 커서(맨 위 z-order)

        # 창이 열리면 음성으로 주문 방법을 안내합니다(배리어프리 핵심).
        self._say(self.tr.t("voice_guide_tts"))
        # 시각장애인 흐름: 안내를 들려준 뒤 마이크를 자동으로 켭니다.
        # (안내 음성이 끝날 때까지 기다렸다가 시작)
        if auto_listen and speech_available():
            QTimer.singleShot(config.VOICE_AUTO_LISTEN_DELAY_MS, self._auto_listen)

    def _auto_listen(self) -> None:
        if self.isVisible():                     # 그 사이 창이 닫혔으면 마이크를 켜지 않음
            self._start_speech()

    def _say(self, text: str) -> None:
        """TTS 엔진이 있으면 문장을 읽어 줍니다(없으면 조용히 무시)."""
        if self.speaker is not None and text:
            self.speaker.say(text)

    # ─────────────────────────────────────
    # 마이크 음성 인식(비동기)
    # ─────────────────────────────────────
    def _start_speech(self) -> None:
        """말하기 버튼: 백그라운드 스레드로 마이크 인식을 시작합니다."""
        if not speech_available():
            return
        if self._worker and self._worker.isRunning():
            return
        self._fails = 0                          # 손님이 직접 다시 시작 → 재시도 횟수 초기화
        self._say(self.tr.t("voice_listen_tts"))
        self.mic_btn.setEnabled(False)
        self.mic_btn.setText("🎙 " + self.tr.t("listening_now"))
        # "지금 말씀해 주세요" 안내가 끝난 뒤에 마이크를 엽니다(안내 소리를 듣지 않게).
        run_when_quiet(self.speaker, self._begin_listen)

    def _begin_listen(self) -> None:
        if not self.isVisible():                 # 그 사이 창이 닫혔으면 마이크를 켜지 않음
            self._reset_mic_button()
            return
        if self._worker and self._worker.isRunning():
            return
        self._worker = SpeechWorker(self.lang, self)   # 대화 중 언어가 바뀌면 그 언어로
        self._worker.status.connect(self.status_label.setText)
        self._worker.recognized.connect(self._on_recognized)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._reset_mic_button)
        self._worker.start()

    def _on_recognized(self, text: str) -> None:
        self.input.setText(text)
        self.status_label.setText(self.tr.t("heard") + text)
        if self._on_text is not None:
            self._handle_text(text)               # 대화식: 확인 버튼 없이 바로 담기
            return
        # 인식 결과를 음성으로 되읽어 주고, 다음 동작을 안내합니다.
        self._say(self.tr.t("voice_heard_tts").format(text=text))

    def _on_failed(self, reason: str) -> None:
        self.status_label.setText("⚠ " + reason)
        self._say(reason)                 # 화면을 못 보는 손님도 다시 말해야 함을 알 수 있게
        if self._auto and self._on_text is not None:
            self._fails += 1
            if self._fails < config.VOICE_LISTEN_RETRIES:
                self._listen_again()          # 못 알아들었으면 자동으로 다시 듣기
            else:
                self._say(self.tr.t("voice_retry_hint_tts"))

    # ── 대화식 주문 ──
    def _submit_input(self) -> None:
        """주문 분석 버튼·Enter: 입력란의 문장을 처리(대화식) 또는 창을 닫고 넘김(기존 방식)."""
        text = self.input.text().strip()
        if not text:
            return
        if self._on_text is not None:
            self._handle_text(text)
        else:
            self.accept()

    def _handle_text(self, text: str) -> None:
        """문장 하나를 장바구니에 반영하고, 결제 요청이면 창을 닫고, 아니면 계속 듣습니다."""
        res = self._on_text(text) or {}
        self.lang = res.get("lang", self.lang)    # 영어로 주문하면 다음부터 영어로 먼저 알아들음
        self.input.clear()
        self._refresh_pay_btn()
        if res.get("checkout"):
            self.checkout_requested = True
            self.accept()
            return
        if res.get("message"):
            self.status_label.setText(res["message"])
        if res.get("understood"):
            self._fails = 0
        if self._auto:
            self._say(Translator(self.lang).t("voice_next_tts"))
            self._listen_again()

    def _listen_again(self) -> None:
        """안내 음성이 끝난 뒤 다시 듣습니다(창이 열려 있을 때만)."""
        if not self.isVisible():
            return
        self.mic_btn.setEnabled(False)
        self.mic_btn.setText("🎙 " + self.tr.t("listening_now"))
        run_when_quiet(self.speaker, self._begin_listen)

    def _request_checkout(self) -> None:
        """결제하기 버튼: 담은 메뉴가 있으면 창을 닫고 바로 결제."""
        if self._can_checkout is not None and not self._can_checkout():
            self.status_label.setText("⚠ " + self.tr.t("cart_empty"))
            self._say(self.tr.t("cart_empty"))
            return
        self.checkout_requested = True
        self.accept()

    def _refresh_pay_btn(self) -> None:
        if self._can_checkout is not None:
            self.pay_btn.setEnabled(bool(self._can_checkout()))

    def _reset_mic_button(self) -> None:
        self.mic_btn.setEnabled(True)
        self.mic_btn.setText("🎙 " + self.tr.t("speak_again"))

    def get_text(self) -> str:
        return self.input.text().strip()

    def receive_gesture(self, name: str) -> None:
        """비전 스레드에서 전달된 제스처를 다이얼로그 내부 동작으로 연결합니다.

        · 선택 손동작(기본: 집게 손) : 입력된 텍스트가 있으면 주문 분석 실행(Accept)
        · swipe_right     : 예시 문장 다음으로 이동
        · swipe_left      : 예시 문장 이전으로 이동
        """
        if name in config.SELECT_GESTURES or name == "select":
            # 집게 손: 커서 아래 버튼(마이크·예시 문장·취소·주문 분석)을 누르고,
            # 버튼을 가리키지 않았으면 입력된 문장으로 바로 주문 분석
            if self._aim is not None:
                target = self._button_under_cursor(*self._aim)
                if target is not None:
                    target.click()
                    return
            if self.input.text().strip():
                self._submit_input()         # 대화식이면 바로 담기, 아니면 창을 닫고 넘김
        elif name == "swipe_right":
            self._cycle_example(+1)
        elif name == "swipe_left":
            self._cycle_example(-1)

    def _cycle_example(self, direction: int) -> None:
        """방향에 따라 예시 문장을 순환해서 입력란에 채워 줍니다."""
        examples = {"ko": self.EXAMPLES_KO, "en": self.EXAMPLES_EN,
                    "zh": self.EXAMPLES_ZH}.get(self.lang, self.EXAMPLES_EN)
        if not examples:
            return
        current = self.input.text().strip()
        try:
            idx = list(examples).index(current)
        except ValueError:
            idx = -1
        next_idx = (idx + direction) % len(examples)
        self.input.setText(examples[next_idx])
        preview = examples[next_idx][:28] + ("…" if len(examples[next_idx]) > 28 else "")
        self.status_label.setText("👆 " + preview)

    # ─────────────────────────────────────
    # 제스처 에임(커서 이동) + 드웰(머무름) 클릭
    # ─────────────────────────────────────
    def receive_aim(self, nx: float, ny: float) -> None:
        """메인 창에서 넘어온 에임 좌표로 창 안 커서를 옮기고 드웰을 진행합니다."""
        self.cursor.move_norm(self.width(), self.height(), nx, ny)
        self._aim = (nx, ny)
        self._update_dwell(nx, ny)

    def _update_dwell(self, nx: float, ny: float) -> None:
        """커서가 한 버튼 위에 DWELL_SELECT_MS 동안 머물면 그 버튼을 자동으로 누릅니다."""
        if not config.DWELL_ENABLED:
            self._reset_dwell()
            return
        target = self._button_under_cursor(nx, ny)
        if getattr(self, "_dwell_lock", None) is not None:   # 방금 누른 버튼 위면 대기
            if target is self._dwell_lock:
                self._reset_dwell()
                return
            self._dwell_lock = None
        if target is None:
            self._reset_dwell()
            return
        now = time.time() * 1000
        moved = ((nx - self._dwell_x) ** 2 + (ny - self._dwell_y) ** 2) ** 0.5
        # 대상이 바뀌었거나 커서가 많이 움직이면 타이머를 새로 시작
        if target is not self._dwell_target or moved > config.DWELL_MOVE_TOLERANCE:
            self._dwell_target = target
            self._dwell_start_ms = now
            self._dwell_x, self._dwell_y = nx, ny
            self.cursor.set_progress(0.0)
            return
        elapsed = now - self._dwell_start_ms
        self.cursor.set_progress(elapsed / config.DWELL_SELECT_MS)
        if elapsed >= config.DWELL_SELECT_MS:
            if now - self._last_dwell_ms < config.GRAB_COOLDOWN_MS:
                return
            self._last_dwell_ms = now
            self._reset_dwell()
            self._dwell_lock = target   # 커서가 벗어날 때까지 같은 버튼 재클릭 금지
            if target.isEnabled():
                target.click()          # 실제 버튼 클릭(마이크/예시/취소/주문 분석/결제)

    def _reset_dwell(self) -> None:
        self._dwell_target = None
        self.cursor.set_progress(0.0)

    def _button_under_cursor(self, nx: float, ny: float) -> QPushButton | None:
        """커서(정규화 좌표) 아래에 있는, 눌러지는 버튼을 찾습니다."""
        px = int(nx * self.width())
        py = int(ny * self.height())
        w = self.childAt(px, py)
        while w is not None:
            if isinstance(w, QPushButton) and w.isEnabled():
                return w
            w = w.parentWidget()
        return None

    def closeEvent(self, event) -> None:
        # 창을 닫을 때 마이크 스레드를 안전하게 정리합니다.
        if self._worker and self._worker.isRunning():
            self._worker.wait(2000)
        super().closeEvent(event)
