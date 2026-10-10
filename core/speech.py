"""
core/speech.py — 음성 안내(TTS) 엔진
================================================
시각장애인·고령자를 위한 '소리로 읽어주기' 기능(배리어프리 핵심).

· pyttsx3(오프라인 TTS)를 쓰며, 없으면 조용히 무시합니다(견고성).
· 말하기는 별도 스레드에서 처리해 UI 가 멈추지 않게 합니다.
"""
from __future__ import annotations

import queue
import threading

from config import TTS_ENABLED, TTS_RATE


class Speaker:
    """문장을 음성으로 읽어주는 클래스(백그라운드 스레드)."""

    def __init__(self):
        self.enabled = TTS_ENABLED
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._engine = None
        self._thread = None
        # 읽는 중이거나 대기 중인 문장 수(마이크를 켤 시점 판단용). 대기열에서 꺼낸 직후의
        # 빈틈 없이 세려고 say() 에서 늘리고, 다 읽은 뒤에 줄입니다.
        self._pending = 0
        self._pending_lock = threading.Lock()
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
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", TTS_RATE)
        except Exception:
            self.enabled = False
            self._engine = None
            return
        self._engine = engine
        # 언어별 최적 음성 매핑(중요): 한국어 문장을 영어 음성으로 읽으면
        # 오디오가 비어 '소리가 나지 않습니다'. 문장 언어에 맞는 음성으로 바꿉니다.
        try:
            voices_by_lang = self._map_voices(engine.getProperty("voices"))
        except Exception:
            voices_by_lang = {}
        while True:
            text = self._queue.get()
            if text is None:                # 종료 신호
                break
            if not self.enabled:            # 도중에 꺼졌으면 조용히 버립니다
                self._done_one()
                continue
            try:
                voice_id = voices_by_lang.get(self._detect_lang(text))
                if voice_id:
                    engine.setProperty("voice", voice_id)
                engine.say(text)
                engine.runAndWait()
            except Exception:
                pass
            finally:
                self._done_one()

    def _done_one(self) -> None:
        with self._pending_lock:
            self._pending = max(0, self._pending - 1)

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
        """문장을 읽도록 대기열에 넣습니다(즉시 반환)."""
        if self.enabled and text:
            with self._pending_lock:
                self._pending += 1
            self._queue.put(text)

    def is_speaking(self) -> bool:
        """읽는 중이거나 읽을 문장이 남아 있으면 True.

        마이크는 이 값이 False 가 된 뒤에 켜야 합니다. 안내 음성이 나오는 동안 켜면
        키오스크 자신의 목소리를 '주변 소음'으로 재서 손님의 짧은 대답('네')을 놓칩니다.
        """
        if not self.enabled:            # TTS 가 없거나 꺼졌으면 기다릴 소리도 없음
            return False
        return self._pending > 0

    def toggle(self, on: bool) -> None:
        self.enabled = on and self._engine is not None

    def shutdown(self) -> None:
        if self._thread:
            self._queue.put(None)
