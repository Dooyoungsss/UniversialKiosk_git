"""
ui/voice_dialog.py — 음성 주문 입력 창 (계획서 2.4)
================================================
마이크로 말하거나(STT) 텍스트로 주문 문장을 입력받아
LLM/룰 기반 NLU 로 분석하는 대화창입니다.

· 🎙 말하기 → 마이크로 말하면 글자로 받아 적어 줍니다(Google STT).
· 마이크 듣기는 별도 스레드(QThread)에서 처리해 화면이 멈추지 않습니다.
· 예시 문장 버튼을 누르면 자동으로 채워져 시연이 편합니다.
· 마이크/인터넷이 없으면 버튼이 비활성화되고 직접 입력으로 안내합니다.
"""
from __future__ import annotations

import importlib.util

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QVBoxLayout)

import config
from core.i18n import Translator

# STT(음성인식)에 쓸 Google 언어 코드(언어별)
STT_LANG_CODE = {"ko": "ko-KR", "en": "en-US", "zh": "zh-CN"}


def speech_available() -> bool:
    """speech_recognition 과 pyaudio 가 모두 설치돼 있는지 확인."""
    return (importlib.util.find_spec("speech_recognition") is not None
            and importlib.util.find_spec("pyaudio") is not None)


class SpeechWorker(QThread):
    """마이크로 듣고 Google STT 로 글자를 받아오는 백그라운드 스레드."""

    # 단계별 상태 메시지 / 성공 결과 / 실패 사유
    status = pyqtSignal(str)
    recognized = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, lang: str, parent=None):
        super().__init__(parent)
        self.lang = lang
        self.tr = Translator(lang)

    def run(self) -> None:
        try:
            import speech_recognition as sr
        except Exception as e:
            self.failed.emit(f"{self.tr.t('mic_lib_missing')}: {e}")
            return
        try:
            recognizer = sr.Recognizer()
            with sr.Microphone() as source:
                # 주변 소음 수준을 잠깐 측정해 인식률을 높입니다(노이즈 보정).
                self.status.emit(self.tr.t("calibrating"))
                recognizer.adjust_for_ambient_noise(source, duration=0.6)
                self.status.emit(self.tr.t("speak_now"))
                audio = recognizer.listen(source, timeout=6, phrase_time_limit=10)
        except Exception:
            # timeout 등: 사용자가 말을 안 했거나 마이크 접근 실패
            self.failed.emit(self.tr.t("no_speech"))
            return

        self.status.emit(self.tr.t("recognizing"))
        try:
            text = recognizer.recognize_google(
                audio, language=STT_LANG_CODE.get(self.lang, "en-US"))
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
        "一份鲜虾汉堡套餐，配菜换成苕士棒",
    ]

    def __init__(self, lang: str, hint: str, listening_text: str, parent=None,
                 speaker=None, auto_listen: bool = False):
        super().__init__(parent)
        self.lang = lang
        self.tr = Translator(lang)
        self.speaker = speaker            # 음성 안내(TTS) 엔진(없으면 조용히 무시)
        self._worker: SpeechWorker | None = None
        self.setWindowTitle("🎤 " + self.tr.t("voice_title"))
        self.setMinimumWidth(640)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(14)

        title = QLabel("🎤 " + self.tr.t("voice_natural"))
        title.setStyleSheet("font-size:22pt; font-weight:800;")
        lay.addWidget(title)

        sub = QLabel(hint)
        sub.setWordWrap(True)
        sub.setStyleSheet("color:#5C6B82;")
        lay.addWidget(sub)

        self.input = QLineEdit()
        self.input.setPlaceholderText(listening_text)
        self.input.setStyleSheet("font-size:18pt; padding:12px; border-radius:12px;"
                                 "border:2px solid #2D6CDF;")
        self.input.returnPressed.connect(self.accept)
        lay.addWidget(self.input)

        # 마이크 상태 안내 줄
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color:#2D6CDF; font-weight:700;")
        lay.addWidget(self.status_label)

        # 예시 문장 버튼들(시연 편의)
        ex_label = QLabel(self.tr.t("examples_label"))
        ex_label.setStyleSheet("color:#5C6B82; font-weight:700;")
        lay.addWidget(ex_label)
        examples = {"ko": self.EXAMPLES_KO, "en": self.EXAMPLES_EN,
                    "zh": self.EXAMPLES_ZH}.get(lang, self.EXAMPLES_EN)
        for ex in examples:
            b = QPushButton(ex)
            b.setObjectName("Ghost")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet("text-align:left; padding:10px;")
            b.clicked.connect(lambda _, t=ex: self.input.setText(t))
            lay.addWidget(b)

        # 실제 마이크 버튼 + 확인/취소
        btn_row = QHBoxLayout()
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
        ok.clicked.connect(self.accept)
        btn_row.addWidget(self.mic_btn)
        btn_row.addStretch()
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok)
        lay.addLayout(btn_row)

        # 손동작 힌트(카메라 제스처로 다이얼로그를 조작할 수 있음을 안내)
        self.gesture_hint_label = QLabel(self.tr.t("voice_gesture_hint"))
        self.gesture_hint_label.setStyleSheet("color:#8A9BAE; font-size:9pt;")
        self.gesture_hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.gesture_hint_label)

        # 창이 열리면 음성으로 주문 방법을 안내합니다(배리어프리 핵심).
        self._say(self.tr.t("voice_guide_tts"))
        # 시각장애인 흐름: 안내를 들려준 뒤 마이크를 자동으로 켭니다.
        # (안내 음성과 겹치지 않도록 잠시 기다렸다가 시작)
        if auto_listen and speech_available():
            QTimer.singleShot(config.VOICE_AUTO_LISTEN_DELAY_MS, self._start_speech)

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
        self._say(self.tr.t("voice_listen_tts"))
        self.mic_btn.setEnabled(False)
        self.mic_btn.setText("🎙 " + self.tr.t("listening_now"))
        self._worker = SpeechWorker(self.lang, self)
        self._worker.status.connect(self.status_label.setText)
        self._worker.recognized.connect(self._on_recognized)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._reset_mic_button)
        self._worker.start()

    def _on_recognized(self, text: str) -> None:
        self.input.setText(text)
        self.status_label.setText(self.tr.t("heard") + text)
        # 인식 결과를 음성으로 되읽어 주고, 다음 동작을 안내합니다.
        self._say(self.tr.t("voice_heard_tts").format(text=text))

    def _on_failed(self, reason: str) -> None:
        self.status_label.setText("⚠ " + reason)

    def _reset_mic_button(self) -> None:
        self.mic_btn.setEnabled(True)
        self.mic_btn.setText("🎙 " + self.tr.t("speak_again"))

    def get_text(self) -> str:
        return self.input.text().strip()

    def receive_gesture(self, name: str) -> None:
        """비전 스레드에서 전달된 제스처를 다이얼로그 내부 동작으로 연결합니다.

        · fist / sign_yes : 입력된 텍스트가 있으면 주문 분석 실행(Accept)
        · swipe_right     : 예시 문장 다음으로 이동
        · swipe_left      : 예시 문장 이전으로 이동
        """
        if name in ("fist", "sign_yes"):
            if self.input.text().strip():
                self.accept()
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

    def closeEvent(self, event) -> None:
        # 창을 닫을 때 마이크 스레드를 안전하게 정리합니다.
        if self._worker and self._worker.isRunning():
            self._worker.wait(2000)
        super().closeEvent(event)
