"""
build_poster.py — 대회 제출용 A0 홍보 포스터(2장) PDF 생성기
================================================
1) 실제 앱 화면을 고해상도(2배)로 캡처합니다(카메라·소리 끔, 통계 DB 미사용) → poster/img/
2) poster/poster.html 을 Edge(없으면 Chrome) 헤드리스로 A0 크기 PDF 로 인쇄합니다.

실행:
    .\.venv\Scripts\python.exe build_poster.py            # 캡처 + PDF
    .\.venv\Scripts\python.exe build_poster.py --pdf-only # 문구만 고쳤을 때(PDF만 다시)
    .\.venv\Scripts\python.exe build_poster.py --drafts --pdf-only  # 3m 거리용 시안 A·B + B 굴림체 판

※ 포스터에는 개인 식별정보(이름·학교명 등)를 넣지 않습니다(대회 요강).
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
POSTER = ROOT / "poster"
IMG = POSTER / "img"
OUT = ROOT / "유니버셜키오스크_홍보포스터_A0.pdf"
DRAFTS = {   # 3m 거리에서 읽히는 큰 글씨 시안(본문 52pt 이상): A 밝은 이야기형, B 고대비 화면 중심형
    "poster_a.html": ROOT / "포스터_시안A_NO PROBLEM KIOSK_A0.pdf",
    "poster_b.html": ROOT / "포스터_시안B_NO PROBLEM KIOSK_A0.pdf",
}
GULIM_OUT = ROOT / "포스터_시안B_굴림체_NO PROBLEM KIOSK_A0.pdf"   # 시안 B 와 같은 내용, 글꼴만 굴림체
BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def capture_screens() -> None:
    """실제 앱의 세로 화면(1080×1920)을 모드·언어별로 캡처합니다(시연 막대·상태 줄·카메라 창은 숨김)."""
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"   # main.py 와 같은 픽셀 기준(디자인 1px = 화면 1px)
    os.environ["QT_FONT_DPI"] = "96"
    os.environ["QT_SCALE_FACTOR"] = "2"             # 인쇄용 2배 해상도(2160×3840)
    sys.path.insert(0, str(ROOT))
    import config
    config.VISION_ENABLED = False
    config.ACCESSIBILITY_INTRO_ENABLED = False
    import core.speech as speech
    speech.TTS_ENABLED = False          # 소리만 끄고, '소리 안내' 버튼은 실제 기본값(켜짐)으로 보이게
    import core.database as database
    database.KioskDatabase.__init__.__defaults__ = (":memory:",)

    from PyQt6.QtCore import Qt, QEvent, QCoreApplication, QPoint, QRect
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    from core import menu_data
    from ui import theme as theme_mod
    from ui.main_window import KioskMainWindow
    from ui.voice_dialog import VoiceOrderDialog
    from ui.widgets import ChoiceDialog

    IMG.mkdir(parents=True, exist_ok=True)
    keep = []                                    # 캡처가 끝날 때까지 창이 사라지지 않게 보관

    def flush() -> None:
        for _ in range(3):
            app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        app.processEvents()

    def save(widget, name: str, region: QRect | None = None) -> None:
        flush()
        (widget.grab(region) if region else widget.grab()).save(str(IMG / name))
        print("  saved", name)

    def window(mode: str, lang: str = "ko", screen: str = "menu", cart: bool = True):
        w = KioskMainWindow()
        w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        w.demo_tag.parentWidget().hide()         # 발표자용 시연 막대
        w.mode_label.parentWidget().hide()       # 인식 상태 줄
        w.cam_view.hide()                        # 카메라 미리보기(손님 얼굴이 비치는 곳)
        w.resize(config.WINDOW_WIDTH, config.WINDOW_HEIGHT)
        w.tr.set_lang(lang)
        w._set_mode(mode)
        w._apply_theme()
        w.show()
        if screen == "menu":
            w._go_menu()
            if cart:
                w._add_to_cart(menu_data.get_item("burger_bulgogi"), is_set=True)
                w._add_to_cart(menu_data.get_item("drink_cola"))
        flush()
        w.toast.hide()
        keep.append(w)
        return w

    # ① 첫 화면 + 접근성 안내 창
    w = window(config.MODE_STANDARD, screen="welcome")
    save(w, "welcome_standard.png")
    box = ChoiceDialog("🦯 " + w.tr.t("a11y_ask_title"), w.tr.t("a11y_ask"),
                       w.tr.t("a11y_yes"), w.tr.t("a11y_no"), style=w.styleSheet(), parent=w)
    box.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    box.show()
    save(box, "a11y_popup.png")
    box.close()

    # ② 나이 인식 자동 화면: 어린이 · 일반 · 실버
    for mode in (config.MODE_CHILD, config.MODE_STANDARD, config.MODE_SILVER):
        save(window(mode), f"menu_{mode}.png")

    # ③ 제스처: 메뉴 위 손바닥 커서 + 드웰 진행 링(메뉴 윗부분 확대)
    w = window(config.MODE_STANDARD)
    card = w.menu_grid.itemAt(1).widget()
    central = w.centralWidget()
    c = card.mapTo(central, card.rect().center())
    nx, ny = c.x() / central.width(), c.y() / central.height()
    w._cursor_nx, w._cursor_ny = nx, ny
    w.cursor.move_norm(central.width(), central.height(), nx, ny)
    w.cursor.set_progress(0.65)
    top = w.cat_buttons[menu_data.CATEGORY_BURGER].mapTo(w, QPoint(0, 0)).y() - 16
    bottom = card.mapTo(w, QPoint(0, card.height())).y() + 14
    save(w, "gesture_dwell.png", QRect(0, top, w.width(), bottom - top))

    # ④ 고대비 + 음성 주문 창
    w = window(config.MODE_HIGH_CONTRAST)
    save(w, "menu_high_contrast.png")
    d = VoiceOrderDialog(w.tr.lang, w.tr.t("voice_hint"), w.tr.t("listening"), w,
                         speaker=None, auto_listen=False,
                         theme=theme_mod.get_theme(w.mode))
    d.setStyleSheet(w.styleSheet())
    d.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    said = "불고기버거 세트 하나 주시고 결제할게요"
    d.input.setText(said)
    d.status_label.setText(w.tr.t("heard") + said)
    d.mic_btn.setText("🎙 " + w.tr.t("speak_again"))
    d.show()
    save(d, "voice_high_contrast.png")
    d.close()

    # ⑤ 다국어: 영어 · 중국어
    for lang in ("en", "zh"):
        save(window(config.MODE_STANDARD, lang=lang), f"menu_{lang}.png")

    for w in keep:
        w.close()
    flush()


def print_pdf(html_path: Path = POSTER / "poster.html", out: Path = OUT) -> None:
    """포스터 HTML 을 A0(841×1189mm) PDF 로 인쇄합니다."""
    browser = next((b for b in BROWSERS if Path(b).exists()), None)
    if browser is None:
        raise SystemExit("Microsoft Edge 또는 Google Chrome 이 필요합니다.")
    html = html_path.resolve().as_uri()
    # Edge 하위 프로세스가 잠시 캐시 파일을 잡고 있을 수 있어, 임시 프로필 삭제 실패는 무시
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
        cmd = [browser, "--headless", "--disable-gpu", "--no-first-run",
               f"--user-data-dir={profile}", "--no-pdf-header-footer",
               "--run-all-compositor-stages-before-draw", "--virtual-time-budget=20000",
               f"--print-to-pdf={out}", html]
        subprocess.run(cmd, check=True, timeout=600,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("SAVED:", out.name, f"({out.stat().st_size / 1e6:.1f} MB)")


def print_gulim(src: Path = POSTER / "poster_b.html", out: Path = GULIM_OUT) -> None:
    """같은 포스터를 굴림체로 인쇄합니다(html.gulim 스타일 사용, 원본 HTML 은 그대로)."""
    tmp = src.with_name("_gulim_" + src.name)   # 같은 폴더여야 img/ 상대 경로가 맞습니다
    html = src.read_text(encoding="utf-8").replace("<html", '<html class="gulim"', 1)
    tmp.write_text(html, encoding="utf-8")
    try:
        print_pdf(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    if "--pdf-only" not in sys.argv:
        capture_screens()
    if "--drafts" in sys.argv:
        for name, out in DRAFTS.items():
            print_pdf(POSTER / name, out)
        print_gulim()
    else:
        print_pdf()
