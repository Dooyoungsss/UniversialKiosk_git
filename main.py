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

import sys


def main() -> int:
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception as e:
        print("PyQt6 가 필요합니다.  pip install PyQt6")
        print("오류:", e)
        return 1

    import config
    from ui.main_window import KioskMainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_TITLE)

    window = KioskMainWindow()
    if config.FULLSCREEN:
        window.showFullScreen()
    else:
        window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
