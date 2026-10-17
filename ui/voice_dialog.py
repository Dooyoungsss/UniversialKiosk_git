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
from core import menu_data
from core.i18n import Translator, josa
from core.yesno import first_transcript, yes_no_answer
from ui.widgets import GestureCursor, VoiceMeter

# STT(음성인식)에 쓸 Google 언어 코드(언어별)
STT_LANG_CODE = {"ko": "ko-KR", "en": "en-US", "zh": "zh-CN"}


def speech_available() -> bool:
    """speech_recognition 과 pyaudio 가 모두 설치돼 있는지 확인."""
    return (importlib.util.find_spec("speech_recognition") is not None
            and importlib.util.find_spec("pyaudio") is not None)


_mic_missing_warned: set[str] = set()      # '못 찾음' 안내를 이미 한 마이크 이름(같은 안내 반복 방지)


def find_mic_index(name: str) -> int | None:
    """이름(일부)이 맞는 마이크의 장치 번호. 비었거나 못 찾으면 None(= Windows 기본 마이크).

    들을 때마다 새로 찾습니다(목록 조회는 0.1초 이내). 결과를 기억해 두면, USB 마이크가 잠깐
    빠졌다가 다시 꽂혔을 때나 장치 번호가 바뀌었을 때 엉뚱한 마이크를 계속 쓰게 되기 때문입니다.
    """
    if not name:
        return None
    try:
        import speech_recognition as sr
        for i, dev in enumerate(sr.Microphone.list_microphone_names()):
            if dev and name.lower() in dev.lower():
                if name in _mic_missing_warned:
                    _mic_missing_warned.discard(name)
                    print(f"[마이크] '{name}' 마이크를 다시 찾았습니다.", flush=True)
                return i
    except Exception:
        pass
    if name not in _mic_missing_warned:      # 연결 상태가 바뀔 때만 한 번 안내
        _mic_missing_warned.add(name)
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


def make_recognizer(sr):
    """말을 끝까지 듣도록 설정한 인식기를 만듭니다."""
    recognizer = sr.Recognizer()
    # 소리 기준값을 낮은 값에서 시작해 주변 소음에 맞춥니다. 기본값(300)에서 시작하면
    # 짧은 측정으로는 충분히 내려오지 않아, 소리가 작은 마이크에서는 '네' 같은 짧은
    # 대답을 말소리로 인정하지 못했습니다. (시끄러운 곳에서는 측정값만큼 올라감)
    recognizer.energy_threshold = 100
    # 말 사이에 VOICE_PAUSE_S 초까지 쉬어도 말이 끝난 것으로 보지 않음(기본 0.8초는
    # "치킨버거 하나… 랑 한우버거"처럼 잠깐 생각하는 사이에 끊겼음)
    recognizer.pause_threshold = config.VOICE_PAUSE_S
    return recognizer


def boost_quiet_audio(sr, audio, max_gain: float = 20.0):
    """녹음 소리가 작으면 키워서 돌려줍니다(최대 max_gain 배, 소리가 찢어지지 않게).

    USB 마이크(USBAudio1.0)는 입력 볼륨을 최대로 해도 소리가 아주 작게 들어와서
    인식기가 말소리를 못 알아듣는 경우가 많았습니다.
    """
    import numpy as np
    if getattr(audio, "sample_width", 0) != 2:
        return audio
    samples = np.frombuffer(audio.frame_data, dtype=np.int16)
    if samples.size == 0:
        return audio
    peak = int(np.abs(samples.astype(np.int32)).max())
    rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
    gain = min(max_gain, 0.7 * 32767 / peak) if peak else 1.0
    _voice_log(f"녹음 소리 크기: 최대 {peak}, 평균 {rms:.0f} → {gain:.1f}배로 키움"
               if gain > 1.3 else f"녹음 소리 크기: 최대 {peak}, 평균 {rms:.0f}")
    if gain <= 1.3:
        return audio
    louder = np.clip(samples.astype(np.float64) * gain, -32768, 32767).astype(np.int16)
    return sr.AudioData(louder.tobytes(), audio.sample_rate, audio.sample_width)


def _voice_log(msg: str) -> None:
    """음성 인식 진행 상황을 콘솔에 남깁니다(VOICE_DEBUG)."""
    if getattr(config, "VOICE_DEBUG", False):
        print(f"[음성인식] {msg}", flush=True)


def run_when_quiet(speaker, callback, min_delay_ms: int = 0, max_wait_ms: int = 20000,
                   beep: bool = False, active=None) -> None:
    """안내 음성(TTS)이 다 끝나고 잠깐 쉰 뒤에 callback 을 부릅니다.

    안내가 나오는 동안 마이크를 켜면 키오스크 자신의 목소리를 '주변 소음'으로 재서
    듣기 기준이 너무 높아지고, 손님의 짧은 대답('네')을 놓치게 됩니다.
    beep=True 면 마이크를 켜기 직전에 '삐' 소리를 내서 지금 말하면 된다는 것을 알립니다
    (질문이 끝나기 전에 대답해서 마이크가 못 듣던 문제).
    active() 가 False 가 되면(그 사이 창이 닫힘) 삐 소리도 내지 않고 그만둡니다.
    """
    start = time.time() * 1000

    def check() -> None:
        if active is not None and not active():
            return
        busy = speaker is not None and speaker.is_speaking()
        if busy and time.time() * 1000 - start < max_wait_ms:
            QTimer.singleShot(150, check)
            return
        if beep and speaker is not None and getattr(speaker, "enabled", False):
            speaker.beep()
            QTimer.singleShot(350, callback)      # 삐(0.18초)가 끝난 뒤 바로 듣기
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
    confidence = pyqtSignal(float)   # 인식기가 매긴 신뢰도 0~1(-1 = 알 수 없음). recognized 직전에 보냄

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
            recognizer = make_recognizer(sr)
            mic_index = find_mic_index(config.MIC_NAME)
            with sr.Microphone(device_index=mic_index) as source:
                if self.short_answer:
                    # 짧은 대답('네'): 소리 크기 기준 없이 정해진 시간 동안 녹음해서 인식기에 맡김
                    self.status.emit(self.tr.t("speak_now"))
                    _voice_log(f"듣는 중(마이크 {mic_index}번, 짧은 대답 "
                               f"{config.SHORT_ANSWER_LISTEN_S}초 녹음)")
                    audio = recognizer.record(source, duration=config.SHORT_ANSWER_LISTEN_S)
                else:
                    # 주변 소음 수준을 잠깐 측정해 인식률을 높입니다(노이즈 보정).
                    self.status.emit(self.tr.t("calibrating"))
                    recognizer.adjust_for_ambient_noise(source, duration=0.8)
                    # 듣는 동안에는 기준을 올리지 않음(말하는 중에 기준이 올라가 작게 말한 부분을
                    # '쉬는 중'으로 보고 말이 끝나기 전에 끊던 문제)
                    recognizer.dynamic_energy_threshold = False
                    self.status.emit(self.tr.t("speak_now"))
                    _voice_log(f"듣는 중(마이크 {mic_index}번, 소리 기준 "
                               f"{recognizer.energy_threshold:.0f}, 주문)")
                    audio = recognizer.listen(source, timeout=6,
                                              phrase_time_limit=config.VOICE_MAX_PHRASE_S)
        except Exception as e:
            # timeout 등: 사용자가 말을 안 했거나 마이크 접근 실패
            _voice_log(f"말소리를 못 들음: {type(e).__name__} {e}")
            self.failed.emit(self.tr.t("no_speech"))
            return

        audio = boost_quiet_audio(sr, audio)       # 작은 소리는 키워서 인식기에 보냄
        self.status.emit(self.tr.t("recognizing"))
        if not self.short_answer:
            self._recognize_order(sr, recognizer, audio)
            return
        self._recognize_short(sr, recognizer, audio)

    def _recognize_short(self, sr, recognizer, audio) -> None:
        """'네/아니요' 같은 짧은 대답: 화면 언어·한국어·영어·중국어로 동시에 인식.

        화면이 영어나 중국어로 바뀌어 있어도 한국어 '네'를 알아듣도록, 언어별 인식 후보를
        ' / ' 로, 언어끼리는 ' || ' 로 이어서 보냅니다(앞쪽 언어부터 판단).
        """
        # 한국어 결과를 먼저 봄: 화면이 영어여도 '네'를 영어 인식기가 'nah'(아니)로 받아 적음
        langs = list(dict.fromkeys(["ko", self.lang, "en", "zh"]))
        results: dict[str, str] = {}
        confs: dict[str, float] = {}
        net_error = []

        def work(lg: str) -> None:
            try:
                res = recognizer.recognize_google(audio, language=STT_LANG_CODE.get(lg, "en-US"),
                                                  show_all=True)
            except sr.RequestError:
                net_error.append(lg)
                return
            except Exception:
                return
            alts = res.get("alternative", []) if isinstance(res, dict) else []
            text = " / ".join(a.get("transcript", "").strip() for a in alts
                              if a.get("transcript", "").strip())
            if text:
                results[lg] = text
                if "confidence" in alts[0]:
                    confs[lg] = float(alts[0]["confidence"])

        threads = [threading.Thread(target=work, args=(lg,), daemon=True) for lg in langs]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        joined = " || ".join(results[lg] for lg in langs if lg in results)
        if joined:
            best = max(confs.values()) if confs else -1.0
            _voice_log(f"짧은 대답 인식: {joined} (인식률 {best:.0%})" if best >= 0
                       else f"짧은 대답 인식: {joined}")
            self.confidence.emit(best)
            self.recognized.emit(joined)
        elif net_error:
            _voice_log("인식 실패: 인터넷 연결 필요")
            self.failed.emit(self.tr.t("internet_required"))   # Google STT 는 온라인 필요
        else:
            _voice_log("인식 실패: 알아들을 수 없음")
            self.failed.emit(self.tr.t("cannot_understand_clear"))

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
        raw_conf: dict[str, float] = {}       # 인식기가 실제로 준 신뢰도(화면 표시용)
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
            if alts and "confidence" in alts[0]:
                raw_conf[lg] = float(alts[0]["confidence"])
            results[lg] = (text, conf) if text else None

        threads = [threading.Thread(target=work, args=(lg,), daemon=True) for lg in langs]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        candidates = [(lg, *results[lg]) for lg in langs if results.get(lg)]
        if not candidates:
            _voice_log("인식 실패: " + ("인터넷 연결 필요" if net_error else "알아들을 수 없음"))
            self.failed.emit(self.tr.t("internet_required") if net_error
                             else self.tr.t("cannot_understand_clear"))
            return
        best = max(candidates, key=lambda c: transcript_score(c[0], c[1], c[2], self.lang))
        _voice_log(f"주문 인식({best[0]}): {best[1]} (인식률 {best[2]:.0%})")
        self.confidence.emit(raw_conf.get(best[0], -1.0))
        self.recognized.emit(best[1])


class VoiceOrderDialog(QDialog):
    """자연어 주문 문장을 입력받는 창."""

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
        self._confirming = False          # '결제할까요?'에 대한 네/아니요를 기다리는 중
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

        # 음성 인식률 막대(들은 말을 얼마나 확실하게 알아들었는지)
        self.voice_meter = VoiceMeter(self.tr.t("voice_meter_title"), self.tr.t("voice_meter_wait"))
        lay.addWidget(self.voice_meter)

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
        self._dwell_lock: QPushButton | None = None    # 방금 드웰로 누른 버튼(커서가 벗어날 때까지 재클릭 금지)
        self.cursor = GestureCursor(self)   # 창 위에 그려지는 손 커서(맨 위 z-order)

        # 창이 열리면 음성으로 주문 방법을 안내합니다(배리어프리 핵심).
        self._say(self.tr.t("voice_guide_tts"))
        names = menu_data.voice_menu_names(lang)
        if names:      # 음성 주문이 버거로 제한돼 있으면 음성으로 주문할 수 있는 메뉴를 알려 줌
            listed = ", ".join(names)
            self._say(self.tr.t("voice_menu_tts").format(names=listed, eul=josa(listed, "을/를")))
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
        # 안내가 끝나면 '삐' 소리를 내고 마이크를 엽니다(안내 소리를 듣지 않게).
        run_when_quiet(self.speaker, self._begin_listen, beep=True, active=self.isVisible)

    def _begin_listen(self) -> None:
        if not self.isVisible():                 # 그 사이 창이 닫혔으면 마이크를 켜지 않음
            self._reset_mic_button()
            return
        if self._worker and self._worker.isRunning():
            return
        # 직전 인식 스레드가 끝나며 버튼을 '다시 말하기'로 되돌렸을 수 있으므로 듣는 중으로 다시 표시
        self.mic_btn.setEnabled(False)
        self.mic_btn.setText("🎙 " + self.tr.t("listening_now"))
        # 대화 중 언어가 바뀌면 그 언어로. '결제할까요?'의 대답은 짧은 대답(네/아니요)으로 들음
        self._worker = SpeechWorker(self.lang, self, short_answer=self._confirming)
        self._worker.status.connect(self.status_label.setText)
        self.voice_meter.set_listening(self.tr.t("listening_now"))
        self._worker.confidence.connect(self.voice_meter.set_confidence)
        self._worker.recognized.connect(self._on_recognized)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._reset_mic_button)
        self._worker.start()

    def _on_recognized(self, text: str) -> None:
        heard = first_transcript(text) if self._confirming else text
        self.voice_meter.set_heard(Translator(self.lang).t("voice_meter_heard").format(text=heard))
        if self._confirming:                      # '결제할까요?'에 대한 대답
            self.input.setText(heard)
            self.status_label.setText(self.tr.t("heard") + heard)
            self._handle_confirm_answer(text)
            return
        self.input.setText(text)
        self.status_label.setText(self.tr.t("heard") + text)
        if self._on_text is not None:
            self._handle_text(text)               # 대화식: 확인 버튼 없이 바로 담기
            return
        # 인식 결과를 음성으로 되읽어 주고, 다음 동작을 안내합니다.
        self._say(self.tr.t("voice_heard_tts").format(text=text))

    def _on_failed(self, reason: str) -> None:
        self.status_label.setText("⚠ " + reason)
        self.voice_meter.set_failed(reason)
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
        if self._confirming:                      # 결제 확인 중에 직접 '네'를 입력한 경우
            self._handle_confirm_answer(text)
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
            # 바로 결제하지 않고 담은 메뉴와 합계를 읽어 준 뒤 '결제할까요?'라고 물어봄
            question = res.get("confirm") or \
                Translator(self.lang).t("checkout_confirm_tts").format(readout="").strip()
            self._ask_checkout(question)
            return
        if res.get("message"):
            self.status_label.setText(res["message"])
        if res.get("understood"):
            self._fails = 0
        else:
            self._fails += 1                      # 들리긴 했지만 주문이 아님(주변 대화 등)도 실패로 셈
        if self._auto:
            if self._fails >= config.VOICE_LISTEN_RETRIES:
                # 계속 못 알아들으면 무한히 듣지 않고 버튼 사용을 안내(마이크 버튼으로 다시 시작)
                self._say(Translator(self.lang).t("voice_retry_hint_tts"))
                return
            self._say(Translator(self.lang).t("voice_next_tts"))
            self._listen_again()

    def _ask_checkout(self, question: str) -> None:
        """'결제' 요청: 담은 메뉴·합계와 함께 '결제할까요?'라고 묻고 네/아니요를 듣습니다."""
        self._confirming = True
        self._fails = 0
        self.status_label.setText("💳 " + question)
        self._say(question)
        if self._auto:
            self._listen_again()

    def _handle_confirm_answer(self, text: str) -> None:
        """'결제할까요?'에 대한 대답: 네 → 결제, 아니요 → 기다림(다시 '결제'라고 하면 또 물음)."""
        tr = Translator(self.lang)
        self.input.clear()
        answer = yes_no_answer(text)
        if answer is True:
            self._confirming = False
            self.checkout_requested = True
            self.accept()
            return
        if answer is False:
            self._confirming = False
            self._fails = 0
            self.status_label.setText(tr.t("checkout_wait_tts"))
            self._say(tr.t("checkout_wait_tts"))
            if self._auto:
                self._listen_again()
            return
        self._fails += 1                          # 네/아니요로 알아듣지 못함 → 다시 물음
        if self._fails >= config.VOICE_LISTEN_RETRIES:
            self._confirming = False              # 다시 '결제'라고 하거나 결제하기 버튼으로
            self._say(tr.t("voice_retry_hint_tts"))
            return
        self.status_label.setText(tr.t("checkout_yesno_tts"))
        self._say(tr.t("checkout_yesno_tts"))
        if self._auto:
            self._listen_again()

    def _listen_again(self) -> None:
        """안내 음성이 끝난 뒤 다시 듣습니다(창이 열려 있을 때만)."""
        if not self.isVisible():
            return
        self.mic_btn.setEnabled(False)
        self.mic_btn.setText("🎙 " + self.tr.t("listening_now"))
        run_when_quiet(self.speaker, self._begin_listen, beep=True, active=self.isVisible)

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

        · 선택 손동작(기본: 집게 손) : 커서 아래 버튼을 누르고, 버튼을 가리키지 않았으면
          입력된 문장으로 주문 분석
        """
        if name in config.SELECT_GESTURES or name == "select":
            # 집게 손: 커서 아래 버튼(마이크·취소·주문 분석·결제하기)을 누르고,
            # 버튼을 가리키지 않았으면 입력된 문장으로 바로 주문 분석
            if self._aim is not None:
                target = self._button_under_cursor(*self._aim)
                if target is not None:
                    target.click()
                    return
            if self.input.text().strip():
                self._submit_input()         # 대화식이면 바로 담기, 아니면 창을 닫고 넘김

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
        if self._dwell_lock is not None:   # 방금 누른 버튼 위면 대기
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
                target.click()          # 실제 버튼 클릭(마이크/취소/주문 분석/결제)

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
