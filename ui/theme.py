"""
ui/theme.py — 화면 테마(색·글자크기) (계획서 2.1 가변 레이아웃)
================================================
사용자 속성에 따라 4가지 모드로 화면이 '지능적으로 변신'합니다.
  · standard      : 일반(기본)
  · silver        : 실버 모드 — 글자/그림 1.5배, 단순한 구성(고령자)
  · child         : 어린이 모드 — 글자 1.3배, 밝은 색, 큰 카드(2열)
  · high_contrast : 고대비 모드 — 검정 배경+노랑·흰 글씨, 글자 1.35배(저시력자)

이벤트 기반 상태 머신(계획서 3장)에서 모드가 바뀌면
get_stylesheet() 로 만든 새 스타일을 화면 전체에 입힙니다.
"""
from __future__ import annotations

from dataclasses import dataclass

from config import (MODE_STANDARD, MODE_SILVER, MODE_CHILD, MODE_HIGH_CONTRAST,
                    SILVER_FONT_SCALE, CHILD_FONT_SCALE)


@dataclass
class Theme:
    """한 가지 모드의 색과 크기 정보를 담는 클래스."""
    name: str
    bg: str                # 배경색
    surface: str           # 카드/패널 색
    primary: str           # 강조색(주 버튼)
    primary_text: str      # 주 버튼 글자색
    text: str              # 일반 글자색
    sub_text: str          # 보조 글자색
    accent: str            # 포인트색(가격 등)
    border: str            # 테두리색
    font_scale: float      # 글자 크기 배율
    base_pt: int = 16      # 기준 글자 크기(pt)

    def pt(self, size: int) -> int:
        """기준 배율을 적용한 글자 크기를 계산합니다."""
        return max(9, int(round(size * self.font_scale)))


THEMES: dict[str, Theme] = {
    MODE_STANDARD: Theme(
        name=MODE_STANDARD,
        bg="#F4F6FB", surface="#FFFFFF", primary="#2D6CDF", primary_text="#FFFFFF",
        text="#1B2330", sub_text="#5C6B82", accent="#E8590C", border="#E2E8F0",
        font_scale=1.0),
    MODE_SILVER: Theme(
        name=MODE_SILVER,
        bg="#FFFDF5", surface="#FFFFFF", primary="#1F7A3D", primary_text="#FFFFFF",
        text="#16240F", sub_text="#3E5237", accent="#C0392B", border="#D7CBB0",
        font_scale=SILVER_FONT_SCALE),                # 1.5배(계획서 2.1)
    MODE_CHILD: Theme(
        name=MODE_CHILD,
        bg="#FFF4FB", surface="#FFFFFF", primary="#F06595", primary_text="#FFFFFF",
        text="#3A2A40", sub_text="#7A5C84", accent="#7048E8", border="#FFD6EC",
        font_scale=CHILD_FONT_SCALE),
    MODE_HIGH_CONTRAST: Theme(
        name=MODE_HIGH_CONTRAST,
        bg="#000000", surface="#101010", primary="#FFD400", primary_text="#000000",
        text="#FFFFFF", sub_text="#FFE066", accent="#00E5FF", border="#FFD400",
        font_scale=1.35),
}


def get_theme(mode: str) -> Theme:
    return THEMES.get(mode, THEMES[MODE_STANDARD])


def get_stylesheet(theme: Theme) -> str:
    """테마 정보를 Qt 스타일시트(QSS) 문자열로 변환합니다."""
    return f"""
    QWidget {{
        background-color: {theme.bg};
        color: {theme.text};
        font-family: 'Malgun Gothic', 'Segoe UI', sans-serif;
        font-size: {theme.pt(16)}pt;
    }}
    QLabel {{
        background-color: transparent;     /* 카드·머리글 위 글자 뒤에 배경색 띠가 생기지 않게 */
    }}
    QLabel#Title {{
        font-size: {theme.pt(34)}pt;
        font-weight: 800;
        color: {theme.text};
    }}
    QLabel#SubTitle {{
        font-size: {theme.pt(18)}pt;
        color: {theme.sub_text};
    }}
    QLabel#Price {{
        color: {theme.accent};
        font-weight: 800;
    }}
    QFrame#Card, QFrame#Panel {{
        background-color: {theme.surface};
        border: 2px solid {theme.border};
        border-radius: 18px;
    }}
    QPushButton {{
        background-color: {theme.surface};
        color: {theme.text};
        border: 2px solid {theme.border};
        border-radius: 14px;
        padding: 10px 16px;
        font-size: {theme.pt(16)}pt;
    }}
    QPushButton:hover {{
        border: 2px solid {theme.primary};
    }}
    QPushButton#Primary {{
        background-color: {theme.primary};
        color: {theme.primary_text};
        border: none;
        font-weight: 800;
        font-size: {theme.pt(20)}pt;
        padding: 16px 22px;
    }}
    QPushButton#Primary:hover {{
        background-color: {theme.accent};
    }}
    QPushButton#MenuCard {{
        background-color: {theme.surface};
        border: 2px solid {theme.border};
        border-radius: 18px;
        text-align: center;
        padding: 12px;
    }}
    QPushButton#MenuCard:hover {{
        border: 3px solid {theme.primary};
        background-color: {theme.bg};
    }}
    QPushButton#Ghost {{
        background-color: transparent;
        border: 2px solid {theme.border};
        color: {theme.sub_text};
    }}
    QPushButton#Ghost:checked {{
        background-color: {theme.primary};
        color: {theme.primary_text};
        border: 2px solid {theme.primary};
    }}
    QPushButton#Danger {{
        background-color: transparent;
        border: 2px solid {theme.accent};
        color: {theme.accent};
    }}
    QLabel#Emoji {{
        font-size: {theme.pt(46)}pt;
    }}
    QLabel#CartTitle {{
        font-size: {theme.pt(22)}pt;
        font-weight: 800;
    }}
    QLabel#Badge {{
        background-color: {theme.primary};
        color: {theme.primary_text};
        border-radius: 12px;
        padding: 4px 10px;
        font-weight: 700;
    }}
    QScrollArea, QScrollArea > QWidget > QWidget {{
        background: transparent;
        border: none;
    }}
    QFrame#StatusBar {{
        background-color: {theme.surface};
        border-top: 2px solid {theme.border};
    }}
    /* ── 세로 27인치(1080×1920) 화면 전용 ── */
    QLabel#Hero {{
        font-size: {theme.pt(44)}pt;
        font-weight: 900;
        color: {theme.text};
    }}
    QLabel#Section {{
        font-size: {theme.pt(22)}pt;
        font-weight: 800;
        color: {theme.text};
    }}
    QLabel#DialogText {{
        font-size: {theme.pt(22)}pt;
        font-weight: 700;
        color: {theme.text};
    }}
    QLabel#OrderNo {{
        font-size: {theme.pt(72)}pt;
        font-weight: 900;
        color: {theme.primary};
    }}
    QLabel#Hint {{
        font-size: {theme.pt(15)}pt;
        color: {theme.sub_text};
    }}
    QLabel#TileEmoji {{
        font-size: {theme.pt(60)}pt;
    }}
    QLabel#TileName {{
        font-size: {theme.pt(20)}pt;
        font-weight: 800;
    }}
    QPushButton#Secondary {{
        background-color: {theme.surface};
        color: {theme.primary};
        border: 3px solid {theme.primary};
        font-weight: 800;
    }}
    QPushButton#Secondary:hover {{
        background-color: {theme.bg};
    }}
    /* 큰 버튼(첫 화면 시작·음성, 메뉴 탭, 결제 등): big 속성이 켜진 버튼 */
    QPushButton[big="true"] {{
        font-size: {theme.pt(24)}pt;
        font-weight: 800;
    }}
    QPushButton#Primary[big="true"] {{
        font-size: {theme.pt(28)}pt;
    }}
    QFrame#Header {{
        background-color: {theme.surface};
        border-bottom: 2px solid {theme.border};
    }}
    QFrame#Header QWidget {{
        background-color: transparent;
    }}
    QFrame#AccessBar {{
        background-color: {theme.surface};
        border-top: 2px solid {theme.border};
    }}
    /* 머리글·접근성 버튼은 모드와 상관없이 같은 크기 → 큰 글씨 모드에서도 화면 폭(1080)을 넘지 않음 */
    QLabel#Logo {{
        font-size: 26pt;
        font-weight: 800;
        color: {theme.text};
    }}
    QLabel#Status {{
        font-size: 13pt;
        color: {theme.sub_text};
    }}
    QPushButton#Access {{
        background-color: {theme.bg};
        color: {theme.text};
        border: 2px solid {theme.border};
        border-radius: 18px;
        padding: 6px 4px;
        font-size: 18pt;
        font-weight: 700;
    }}
    QPushButton#Access:checked {{
        background-color: {theme.primary};
        color: {theme.primary_text};
        border: 2px solid {theme.primary};
    }}
    """
