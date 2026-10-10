"""
main.py — 유니버셜 키오스크 실행 진입점
================================================
팀명 : NO PROBLEM KIOSK
작품 : 유니버셜 키오스크 (모두를 위한 배리어프리 AI 키오스크)

실행 방법:
    python main.py

세 파트로 나뉜 시스템을 하나로 실행합니다(계획서 3장):
  · 비전 백엔드(QThread) + AI 연산  → core/
  · 동적 GUI(PyQt6)                → ui/
"""
from __future__ import annotations

import os
import sys


def _monitor_sizes() -> list[tuple[int, int, int, int]]:
    """연결된 모니터들의 (가로, 세로, 작업영역 가로, 작업영역 세로) 픽셀 크기(Windows, 실패하면 빈 목록).

    작업영역 = 작업 표시줄을 뺀, 창을 놓을 수 있는 영역입니다.
    """
    try:
        import ctypes
        from ctypes import wintypes

        class _MonitorInfo(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

        sizes: list[tuple[int, int, int, int]] = []
        proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
                                       ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

        def _collect(monitor, _dc, _rect, _data):
            info = _MonitorInfo()
            info.cbSize = ctypes.sizeof(_MonitorInfo)
            ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(info))
            m, wk = info.rcMonitor, info.rcWork
            sizes.append((m.right - m.left, m.bottom - m.top,
                          wk.right - wk.left, wk.bottom - wk.top))
            return True

        ctypes.windll.user32.EnumDisplayMonitors(None, None, proc_type(_collect), 0)
        return sizes
    except Exception:
        return []


def _configure_display(design_width: int, design_height: int, fullscreen: bool) -> None:
    """디자인(세로 1080×1920)을 실제 화면에 맞춥니다. QApplication 생성 전에 호출.

    · 세로 모니터(스탠바이미)가 디자인과 같으면 1px = 1px 그대로.
    · 세로 모니터 해상도가 더 작으면(예: 768×1366) 화면 전체를 비율대로 줄여서,
      메인 화면과 안내창·음성 주문 창이 화면 밖으로 튀어나가지 않게 합니다.
    · 세로 모니터가 없으면(개발용 노트북) 세로 화면을 축소해 미리보기로 띄웁니다.
    """
    # Windows 화면 배율(125% 등)과 상관없이 디자인 1px = 화면 1px, 글자는 96DPI 기준
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")
    os.environ.setdefault("QT_FONT_DPI", "96")
    if "QT_SCALE_FACTOR" in os.environ:
        return
    sizes = _monitor_sizes()
    if not sizes:
        return
    portrait = [s for s in sizes if s[1] > s[0]]
    if portrait:
        w, h, work_w, work_h = max(portrait, key=lambda s: s[1])
        if not fullscreen:                  # 창 모드: 작업 표시줄·제목 표시줄 자리를 비움
            w, h = work_w, work_h - 40
        scale = min(1.0, w / design_width, h / design_height)
        if scale < 0.999:
            os.environ["QT_SCALE_FACTOR"] = f"{scale:.3f}"
        return
    tallest = max(s[1] for s in sizes)
    os.environ["QT_SCALE_FACTOR"] = f"{min(1.0, (tallest - 140) / design_height):.3f}"


def main() -> int:
    import config
    _configure_display(config.WINDOW_WIDTH, config.WINDOW_HEIGHT, config.FULLSCREEN)
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception as e:
        print("PyQt6 가 필요합니다.  pip install PyQt6")
        print("오류:", e)
        return 1

    from ui.main_window import KioskMainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_TITLE)

    window = KioskMainWindow()
    portrait = next((s for s in app.screens()
                     if s.geometry().height() > s.geometry().width()), None)
    if config.FULLSCREEN and portrait is not None:
        window.move(portrait.geometry().topLeft())
        window.showFullScreen()
    else:
        # 개발용 미리보기: 주 화면 위쪽 가운데에 세로 창을 통째로 보이게 둠
        avail = app.primaryScreen().availableGeometry()
        window.move(avail.left() + max(0, (avail.width() - window.width()) // 2), avail.top())
        window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
