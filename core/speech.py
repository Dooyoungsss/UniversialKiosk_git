"""
core/speech.py — 음성 안내(TTS) 엔진
================================================
시각장애인·고령자를 위한 '소리로 읽어주기' 기능(배리어프리 핵심).

· pyttsx3(오프라인 TTS)를 쓰며, 없으면 조용히 무시합니다(견고성).
· 말하기는 별도 스레드에서 처리해 UI 가 멈추지 않게 합니다.
"""
from __future__ import annotations

import array
import math
import os
import sys
import tempfile
import threading
import time
import wave
from collections import deque
from types import SimpleNamespace

import config
from config import TTS_ENABLED, TTS_RATE


_BEEP = "\x00beep"        # 대기열 안의 '삐' 소리 표시(문장과 구별)


def _beep_wav() -> str:
    """'삐' 소리 파일(0.18초, 880Hz)을 임시 폴더에 한 번 만들고 경로를 돌려줍니다."""
    path = os.path.join(tempfile.gettempdir(), "kiosk_beep.wav")
    if not os.path.exists(path):
        rate, secs, freq = 22050, 0.18, 880.0
        n = int(rate * secs)
        fade = int(rate * 0.015)                   # 딸깍 소리가 나지 않게 앞뒤를 부드럽게
        samples = array.array("h")
        for i in range(n):
            env = min(1.0, i / fade, (n - i) / fade)
            samples.append(int(14000 * env * math.sin(2 * math.pi * freq * i / rate)))
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(samples.tobytes())
    return path


class _SapiVoice:
    """Windows 음성 엔진(SAPI)을 직접 부르는 말하기 엔진.

    pyttsx3 2.99 는 Windows 에서 '첫 문장만' 소리가 나고, 그다음 문장부터는 말하지 않고
    바로 끝나 버리는 버그가 있습니다(두 번째 안내부터 소리가 안 나던 원인).
    그래서 SAPI 를 직접 써서 문장마다 끝까지 읽습니다(읽는 동안 이 스레드는 기다림).
    """

    def __init__(self, rate_wpm: int):
        import comtypes
        import comtypes.client
        comtypes.CoInitialize()                    # 이 스레드에서 COM 사용 준비
        self.tts = comtypes.client.CreateObject("SAPI.SpVoice")
        # pyttsx3 와 같은 환산식(분당 단어 수 → SAPI 속도 -10~10)으로 말하기 속도를 맞춤
        self._rate = max(-10, min(10, int(math.log(rate_wpm / 156.63, 1.11))))
        self.tts.Rate = self._rate
        self._tokens = {}
        self.voices = []
        tokens = self.tts.GetVoices()
        for i in range(tokens.Count):
            tok = tokens.Item(i)
            self._tokens[tok.Id] = tok
            self.voices.append(SimpleNamespace(id=tok.Id, name=tok.GetDescription()))
        self._voice_id = None

    def set_voice(self, voice_id: str) -> None:
        tok = self._tokens.get(voice_id)
        if tok is not None and voice_id != self._voice_id:
            self.tts.Voice = tok
            self.tts.Rate = self._rate             # 목소리를 바꾸면 속도가 초기화되므로 다시 지정
            self._voice_id = voice_id

    def beep(self) -> None:
        """'삐' 소리를 음성 안내와 같은 스피커로 냅니다(마이크가 켜지는 순간을 알림)."""
        import comtypes.client
        stream = comtypes.client.CreateObject("SAPI.SpFileStream")
        stream.Open(_beep_wav(), 0)
        try:
            self.tts.SpeakStream(stream, 0)
        finally:
            stream.Close()

    def speak(self, text: str, should_stop=lambda: False) -> bool:
        """끝까지 읽으면 True, 중간에 멈추라는 요청(새 안내)이 와서 끊었으면 False."""
        self.tts.Speak(text, 1)                    # 1: 비동기로 읽기 시작
        while not self.tts.WaitUntilDone(100):     # 0.1초마다 '멈춤' 요청이 왔는지 확인
            if should_stop():
                self.tts.Speak("", 3)              # 1|2: 지금 읽는 문장을 버리고 멈춤
                return False
        return True


class _Pyttsx3Voice:
    """Windows 가 아닐 때(또는 SAPI 를 못 열 때) 쓰는 pyttsx3 엔진."""

    tts = None                                     # 출력 스피커 선택은 SAPI 에서만 지원

    def beep(self) -> None:
        pass                                       # pyttsx3 에는 소리 파일 재생이 없음

    def __init__(self, rate_wpm: int):
        import pyttsx3
        self.engine = pyttsx3.init()
        self.engine.setProperty("rate", rate_wpm)
        self.voices = self.engine.getProperty("voices")

    def set_voice(self, voice_id: str) -> None:
        self.engine.setProperty("voice", voice_id)

    def speak(self, text: str, should_stop=lambda: False) -> bool:
        self.engine.say(text)                      # pyttsx3 는 중간에 끊지 못함
        self.engine.runAndWait()
        return True


class Speaker:
    """문장을 음성으로 읽어주는 클래스(백그라운드 스레드)."""

    def __init__(self):
        self.enabled = TTS_ENABLED
        self._items: deque = deque()           # 아직 읽지 않은 문장들(None = 종료 신호)
        self._cv = threading.Condition()       # 대기열·읽는 중 상태를 함께 지키는 잠금
        self._busy = False                     # 지금 문장을 읽는 중인지
        self._interrupt = threading.Event()    # 읽는 중인 문장을 멈추라는 요청(say_now)
        self._engine = None
        self._thread = None
        self._output_desc: str | None = None   # 지금 소리를 내보내는 스피커 이름
        self._output_missing = False           # 지정한 스피커를 못 찾았다고 이미 알렸는지
        if self.enabled:
            self._start()

    def _start(self) -> None:
        # 엔진 생성과 발화를 '반드시 같은 스레드'에서 하도록, 엔진은 _loop 안에서
        # 만듭니다. Windows SAPI5(COM)는 엔진을 만든 스레드와 다른 스레드에서
        # runAndWait 를 호출하면 소리가 나지 않거나 멈추는 고질적 문제가 있습니다.
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        # 실제로 말하는 이 스레드 안에서 엔진을 초기화합니다(핵심).
        engine = self._make_engine()
        if engine is None:
            self.enabled = False
            self._engine = None
            return
        self._engine = engine
        # 언어별 최적 음성 매핑(중요): 한국어 문장을 영어 음성으로 읽으면
        # 오디오가 비어 '소리가 나지 않습니다'. 문장 언어에 맞는 음성으로 바꿉니다.
        try:
            voices_by_lang = self._map_voices(engine.voices)
        except Exception:
            voices_by_lang = {}
        while True:
            with self._cv:
                while not self._items:
                    self._cv.wait()
                text = self._items.popleft()
                if text is None:            # 종료 신호
                    break
                if not self.enabled:        # 도중에 꺼졌으면 조용히 버립니다
                    continue
                self._interrupt.clear()     # 이 문장부터 새로 읽음
                self._busy = True
            try:
                if engine.tts is not None:
                    self._select_output(engine.tts)
                if text is _BEEP:
                    engine.beep()
                    if getattr(config, "VOICE_DEBUG", False):
                        print("[음성안내] 삐 (마이크 켬)", flush=True)
                    continue
                voice_id = voices_by_lang.get(self._detect_lang(text))
                if voice_id:
                    engine.set_voice(voice_id)
                started = time.time()
                finished = engine.speak(text, self._interrupt.is_set)
                if getattr(config, "VOICE_DEBUG", False):
                    cut = "" if finished else ", 새 안내로 끊음"
                    print(f"[음성안내] ({time.time() - started:.1f}초{cut}) {text}", flush=True)
            except Exception as e:
                print(f"[음성안내] 말하기 실패: {type(e).__name__}: {e} / {text}", flush=True)
            finally:
                with self._cv:
                    self._busy = False

    @staticmethod
    def _make_engine():
        """말하기 엔진을 만듭니다. Windows 는 SAPI 직접, 그 밖에는 pyttsx3."""
        if sys.platform == "win32":
            try:
                return _SapiVoice(TTS_RATE)
            except Exception as e:
                print(f"[음성안내] Windows 음성 엔진을 열지 못해 pyttsx3 로 대신합니다: {e}",
                      flush=True)
        try:
            return _Pyttsx3Voice(TTS_RATE)
        except Exception as e:
            print(f"[음성안내] 음성 안내를 쓸 수 없습니다: {e}", flush=True)
            return None

    def _select_output(self, tts) -> None:
        """음성 안내를 SPEAKER_NAME 스피커로 내보냅니다(없으면 Windows 기본 스피커).

        Windows 기본 출력 장치가 바뀌어도 키오스크 안내는 항상 지정한 스피커로 나갑니다.
        블루투스 스피커는 끊겼다 다시 연결될 수 있어 말할 때마다 다시 찾습니다.
        블루투스의 '핸즈프리(Hands-Free)' 장치는 통화용이라 음질이 나빠 쓰지 않습니다.
        """
        name = (getattr(config, "SPEAKER_NAME", "") or "").strip().lower()
        if not name:
            return
        try:
            outs = tts.GetAudioOutputs()          # Windows SAPI 음성 객체
        except Exception:
            return                                # SAPI 가 아니면(다른 OS) 기본 스피커 그대로
        for i in range(outs.Count):
            token = outs.Item(i)
            desc = token.GetDescription()
            if name in desc.lower() and "hands-free" not in desc.lower():
                if self._output_missing:
                    print(f"[스피커] '{config.SPEAKER_NAME}' 스피커를 다시 찾았습니다.", flush=True)
                    self._output_missing = False
                if self._output_desc != desc:
                    tts.AudioOutput = token
                    self._output_desc = desc
                return
        if not self._output_missing:
            print(f"[스피커] '{config.SPEAKER_NAME}' 스피커를 찾지 못해 Windows 기본 스피커로 "
                  f"안내합니다.", flush=True)
            self._output_missing = True
        if self._output_desc is not None:
            tts.AudioOutput = None                # 기본 스피커로 되돌림
            self._output_desc = None

    @staticmethod
    def _map_voices(voices) -> dict:
        """설치된 음성들을 언어(ko/en/zh)별 대표 음성 id 로 분류합니다."""
        by_lang: dict[str, str] = {}
        for v in voices or []:
            blob = f"{getattr(v, 'id', '')} {getattr(v, 'name', '') or ''}".upper()
            if any(k in blob for k in ("KO-KR", "KOREAN", "HEAMI")):
                by_lang.setdefault("ko", v.id)
            elif any(k in blob for k in ("ZH-", "CHINESE", "HUIHUI", "YAOYAO",
                                          "KANGKANG", "MANDARIN")):
                by_lang.setdefault("zh", v.id)
            elif any(k in blob for k in ("EN-", "ENGLISH", "DAVID", "ZIRA", "MARK")):
                by_lang.setdefault("en", v.id)
        return by_lang

    @staticmethod
    def _detect_lang(text: str) -> str:
        """문장에서 언어를 추정합니다(한글 우선 → 한자 → 그 외 영어)."""
        for ch in text:
            o = ord(ch)
            if 0xAC00 <= o <= 0xD7A3 or 0x1100 <= o <= 0x11FF or 0x3130 <= o <= 0x318F:
                return "ko"
        for ch in text:
            if 0x4E00 <= ord(ch) <= 0x9FFF:
                return "zh"
        return "en"

    def say(self, text: str) -> None:
        """문장을 읽도록 대기열에 넣습니다(즉시 반환). 앞의 안내가 끝난 뒤 이어서 읽습니다."""
        if self.enabled and text:
            with self._cv:
                self._items.append(text)
                self._cv.notify()

    def beep(self) -> None:
        """앞의 안내가 끝난 뒤 '삐' 소리를 냅니다(이 소리 뒤에 마이크가 켜짐)."""
        if self.enabled:
            with self._cv:
                self._items.append(_BEEP)
                self._cv.notify()

    def stop(self) -> None:
        """읽고 있는 문장을 멈추고, 아직 읽지 않은 문장도 버립니다."""
        with self._cv:
            self._items.clear()
            if self._busy:
                self._interrupt.set()

    def say_now(self, text: str) -> None:
        """앞서 쌓인 안내를 끊고 이 문장을 바로 읽습니다.

        메뉴를 빠르게 여러 번 담으면 '○○이 담겼습니다'가 줄줄이 쌓여 한참 늦게 나오던
        문제를 막습니다. 이어서 들려줘야 하는 안내는 say() 로 뒤에 붙입니다.
        """
        if self.enabled and text:
            self.stop()
        self.say(text)

    def is_speaking(self) -> bool:
        """읽는 중이거나 읽을 문장이 남아 있으면 True.

        마이크는 이 값이 False 가 된 뒤에 켜야 합니다. 안내 음성이 나오는 동안 켜면
        키오스크 자신의 목소리를 '주변 소음'으로 재서 손님의 짧은 대답('네')을 놓칩니다.
        """
        if not self.enabled:            # TTS 가 없거나 꺼졌으면 기다릴 소리도 없음
            return False
        with self._cv:
            return self._busy or bool(self._items)

    def toggle(self, on: bool) -> None:
        self.enabled = on and self._engine is not None
        if not self.enabled:
            self.stop()                 # 소리 안내를 끄면 읽던 문장도 바로 멈춤

    def shutdown(self) -> None:
        if self._thread:
            self.stop()
            with self._cv:
                self._items.append(None)
                self._cv.notify()
