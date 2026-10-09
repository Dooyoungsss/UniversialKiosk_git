"""
build_pptx_step2.py — Step 2(중급) 발표 PPT + 퀴즈 100
================================================
Step 1(기초)을 마친 학생용. 같은 주제를 '원리·숫자·코드 개념'까지 한 단계 깊게.
build_pptx.py의 도구(마스코트·도형·PPT 헬퍼)를 재사용.
실행:  .\.venv\Scripts\python.exe build_pptx_step2.py
"""
from __future__ import annotations
import os, shutil

import build_pptx as B
B.ASSET = "_p2_assets"

# 자주 쓰는 것 별칭
fig_ax, save, rbox, T, arrow, mascot, bubble, wrapt = (
    B.fig_ax, B.save, B.rbox, B.T, B.arrow, B.mascot, B.bubble, B.wrap)
Circle, Arc, Wedge, Polygon, Rectangle = B.Circle, B.Arc, B.Wedge, B.Polygon, B.Rectangle
PRIMARY, ACCENT, GREEN, YELLOW, PINK, INK, GRAY, BG = (
    B.PRIMARY, B.ACCENT, B.GREEN, B.YELLOW, B.PINK, B.INK, B.GRAY, B.BG)
bg, band, textbox, picture, blank, set_run, RGB = (
    B.bg, B.band, B.textbox, B.picture, B.blank, B.set_run, B.RGB)
sym_camera, sym_face = B.sym_camera, B.sym_face

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE


# 여러 박스를 한 줄로(파이프라인)
def boxes_row(ax, items, y=4.7, x0=1.2, x1=14.8, h=1.7, fs=13):
    n = len(items); w = (x1 - x0) / n
    prev = None
    for i, (txt, c) in enumerate(items):
        cx = x0 + w * (i + 0.5)
        rbox(ax, cx - w * 0.43, y - h / 2, w * 0.86, h, fc="white", ec=c, lw=2.5)
        T(ax, cx, y, wrapt(txt, 12), fs=fs, color=INK)
        if prev is not None:
            arrow(ax, (prev, y), (cx - w * 0.43, y), color=INK, lw=3)
        prev = cx + w * 0.43
    return w


def col_boxes(ax, items, x=8.0, y0=6.4, dy=1.15, w=8.6, h=0.95, fs=13):
    prev = None
    for i, (txt, c) in enumerate(items):
        cy = y0 - i * dy
        rbox(ax, x - w / 2, cy - h / 2, w, h, fc="white", ec=c, lw=2.2, rad=0.15)
        T(ax, x, cy, txt, fs=fs, color=INK)
        if prev is not None:
            arrow(ax, (x, prev - h / 2), (x, cy + h / 2), color=INK, lw=2.5)
        prev = cy


# ══════════════════════════════════════════════
# Step 2 그림들
# ══════════════════════════════════════════════
def sc_cover():
    fig, ax = fig_ax("#E3F0DC")
    mascot(ax, 3.0, 4.2, 1.4, say="이제 한 단계 더 깊이!")
    for i, c in enumerate([PRIMARY, ACCENT, GREEN]):
        rbox(ax, 10.5, 5.6 - i * 1.5, 4.4, 1.1, fc="white", ec=c, lw=3)
        T(ax, 12.7, 6.15 - i * 1.5, ["원리", "숫자", "코드 개념"][i], fs=16, color=c)
    T(ax, 9.0, 8.0, "유니버셜 키오스크 · STEP 2", fs=28, color=GREEN)
    T(ax, 9.0, 1.1, "중급: 어떻게 작동하는지 자세히", fs=17, color=INK)
    return save(fig, "s2_cover")


def sc_welcome():
    fig, ax = fig_ax()
    rbox(ax, 1.0, 4.0, 6.2, 3.2, fc="#EAF1FF", ec=PRIMARY, lw=3)
    T(ax, 4.1, 6.6, "Step 1에서 배운 것", fs=16, color=PRIMARY)
    T(ax, 4.1, 5.4, "얼굴→숫자 · 손동작 · 말로 주문\n(비유로 이해)", fs=14)
    arrow(ax, (7.4, 5.6), (8.8, 5.6), color=ACCENT, lw=5)
    rbox(ax, 9.0, 4.0, 6.0, 3.2, fc="#EAF7EF", ec=GREEN, lw=3)
    T(ax, 12.0, 6.6, "Step 2에서 배울 것", fs=16, color=GREEN)
    T(ax, 12.0, 5.4, "왜·어떻게 · 실제 숫자·순서\n(원리로 이해)", fs=14)
    mascot(ax, 8.0, 2.0, 0.6)
    T(ax, 8.0, 0.9, "비유 → 원리로 레벨업!", fs=17, color=INK)
    return save(fig, "s2_welcome")


def sc_arch():
    fig, ax = fig_ax()
    sym_camera(ax, 2.4, 6.0, 0.7)
    rbox(ax, 4.2, 5.0, 3.4, 2.0, fc="#FFF1E6", ec=ACCENT, lw=3)
    T(ax, 5.9, 6.4, "VisionThread", fs=15, color=ACCENT)
    T(ax, 5.9, 5.6, "(별도 스레드)", fs=12)
    arrow(ax, (2.9, 6.0), (4.2, 6.0), color=INK, lw=3)
    sigs = ["age_group", "face_present", "gesture", "frame_ready", "status"]
    for i, sname in enumerate(sigs):
        rbox(ax, 8.0, 6.4 - i * 0.9, 2.9, 0.7, fc="white", ec=GRAY, lw=1.8, rad=0.12)
        T(ax, 9.45, 6.75 - i * 0.9, sname, fs=12, color=PRIMARY)
        arrow(ax, (7.6, 6.0), (8.0, 6.75 - i * 0.9), color=GRAY, lw=1.5)
    rbox(ax, 11.4, 4.4, 3.6, 3.2, fc="#EAF1FF", ec=PRIMARY, lw=3)
    T(ax, 13.2, 6.6, "UI 스레드", fs=15, color=PRIMARY)
    T(ax, 13.2, 5.6, "화면·장바구니\n·테마", fs=13)
    for i in range(5):
        arrow(ax, (10.9, 6.75 - i * 0.9), (11.4, 5.9), color=GRAY, lw=1.2)
    T(ax, 8.0, 1.2, "카메라 스레드가 5가지 '시그널'로 UI에 알려줘요", fs=17, color=INK)
    return save(fig, "s2_arch")


def sc_frame():
    fig, ax = fig_ax()
    boxes_row(ax, [("카메라 읽기", GRAY), ("좌우반전 flip", PRIMARY), ("밝기보정 CLAHE", ACCENT),
                   ("얼굴 468점", GREEN), ("손 21점", PINK), ("시그널 emit", PRIMARY)], y=4.9)
    mascot(ax, 13.6, 7.0, 0.5)
    T(ax, 8.0, 2.6, "연령 추론은 무거워서 3프레임마다 1번만!", fs=15, color=ACCENT)
    T(ax, 8.0, 1.3, "한 프레임이 처리되는 순서 (초당 약 60장)", fs=17, color=INK)
    return save(fig, "s2_frame")


def sc_embed():
    fig, ax = fig_ax()
    sym_face(ax, 2.6, 5.2, 1.3)
    steps = [("① 코(1번)를 원점으로 → 위치 무관", PRIMARY),
             ("② 가장 먼 거리로 나눔 → 크기 무관", ACCENT),
             ("③ 중요한 24개 점만 → (x,y,z)", GREEN),
             ("④ 크기 1로 정규화 → 방향만 남김", PINK)]
    col_boxes(ax, steps, x=9.6, y0=6.6, dy=1.1, w=8.4, h=0.9, fs=13)
    rbox(ax, 1.4, 2.4, 4.0, 1.2, fc="#EAF1FF", ec=PRIMARY, lw=2.5)
    T(ax, 3.4, 3.0, "= 72차원 숫자", fs=15, color=PRIMARY)
    T(ax, 8.0, 1.1, "얼굴 랜드마크 → 72개 숫자(임베딩) 만들기", fs=17, color=INK)
    return save(fig, "s2_embed")


def sc_cosine():
    fig, ax = fig_ax()
    rbox(ax, 3.0, 5.4, 10.0, 1.7, fc="#EAF1FF", ec=PRIMARY, lw=3)
    T(ax, 8.0, 6.25, "cos θ = (a · b) / ( |a| × |b| )", fs=22, color=PRIMARY)
    T(ax, 8.0, 4.4, "정규화(크기 1)하면 → 그냥 a·b (내적) 한 번!", fs=15, color=ACCENT)
    T(ax, 4.0, 3.3, "1에 가까움 = 같은 사람", fs=14, color=GREEN)
    T(ax, 12.0, 3.3, "0 근처 = 남남", fs=14, color=PINK)
    mascot(ax, 8.0, 2.0, 0.55)
    T(ax, 8.0, 0.9, "코사인 유사도: 값 범위 -1~1, 방향으로 닮음 측정", fs=16, color=INK)
    return save(fig, "s2_cosine")


def sc_eucvs():
    fig, ax = fig_ax()
    rbox(ax, 1.2, 3.0, 6.5, 4.0, fc="#FFF7F0", ec=ACCENT, lw=3)
    T(ax, 4.45, 6.4, "유클리드 거리", fs=17, color=ACCENT)
    T(ax, 4.45, 5.2, "두 점의 직선 거리\n√Σ(ai - bi)²", fs=14)
    T(ax, 4.45, 3.7, "밝기·크기에 민감!", fs=13, color="#c0392b")
    rbox(ax, 8.3, 3.0, 6.5, 4.0, fc="#EFFaf3", ec=GREEN, lw=3)
    T(ax, 11.55, 6.4, "코사인 유사도", fs=17, color=GREEN)
    T(ax, 11.55, 5.2, "방향(패턴)만 비교\n크기 잡음에 강함", fs=14)
    T(ax, 11.55, 3.7, "얼굴 비교에 딱 맞아요", fs=13, color=GREEN)
    T(ax, 8.0, 1.2, "왜 코사인? 얼굴은 '방향(패턴)'이 정체성이라서", fs=17, color=INK)
    return save(fig, "s2_eucvs")


def sc_meanface():
    fig, ax = fig_ax()
    T(ax, 8.0, 7.8, "평균 얼굴 빼기 = 오인식을 막은 핵심", fs=18, color=INK)
    rbox(ax, 1.0, 4.6, 6.6, 2.2, fc="#FFECEC", ec="#e05a5a", lw=3)
    T(ax, 4.3, 6.1, "그냥 비교하면", fs=14, color="#c0392b")
    T(ax, 4.3, 5.1, "남남도 0.95↑ (다 닮아 보임)", fs=14)
    arrow(ax, (7.8, 5.7), (9.2, 5.7), color=ACCENT, lw=5)
    T(ax, 8.5, 6.3, "평균 빼기", fs=13, color=ACCENT)
    rbox(ax, 9.4, 4.6, 6.4, 2.2, fc="#EAF7EF", ec=GREEN, lw=3)
    T(ax, 12.6, 6.1, "개인차만 비교", fs=14, color=GREEN)
    T(ax, 12.6, 5.1, "남남은 0.3 미만 → 확실히 구별", fs=13)
    T(ax, 8.0, 3.2, "q = 정규화( 내 얼굴 - 평균 얼굴 )", fs=16, color=PRIMARY)
    mascot(ax, 8.0, 1.7, 0.5)
    return save(fig, "s2_meanface")


def sc_regpipe():
    fig, ax = fig_ax()
    boxes_row(ax, [("임베딩", PRIMARY), ("평균 빼기 project", ACCENT),
                   ("모든 단골과 코사인", GREEN), ("임계값 넘음?", YELLOW),
                   ("연속 8프레임", PINK), ("단골 확정!", GREEN)], y=5.0)
    T(ax, 8.0, 2.8, "임계값: 평균 있으면 0.70 / 없으면 0.999(거의 동일만)", fs=14, color=ACCENT)
    T(ax, 8.0, 1.3, "단골 인식 파이프라인", fs=17, color=INK)
    mascot(ax, 1.6, 7.1, 0.45)
    return save(fig, "s2_regpipe")


def sc_safety3():
    fig, ax = fig_ax()
    items = [("① 평균 얼굴 빼기", "공통 성분 제거", PRIMARY),
             ("② 연속 8프레임", "우연 일치 방지", ACCENT),
             ("③ 임계값 0.999", "기준 없을 땐 초엄격", GREEN)]
    for i, (t, s, c) in enumerate(items):
        x = 3.0 + i * 5.0
        rbox(ax, x - 2.2, 3.4, 4.4, 3.2, fc="white", ec=c, lw=3)
        ax.add_patch(Circle((x, 5.8), 0.55, fc=c, ec=c, zorder=3))
        T(ax, x, 5.8, str(i + 1), fs=22, color="white")
        T(ax, x, 4.7, t.split(' ',1)[1], fs=14, color=c)
        T(ax, x, 3.9, wrapt(s, 10), fs=12)
    T(ax, 8.0, 7.7, "처음 온 손님을 단골로 오인식하지 않는 3중 안전장치", fs=16, color=INK)
    T(ax, 8.0, 1.2, "세 겹으로 막아요", fs=16, color=INK)
    return save(fig, "s2_safety3")


def sc_agecnn():
    fig, ax = fig_ax()
    boxes_row(ax, [("얼굴 자르기 +여백20%", GRAY), ("227×227 blob\n(평균 빼기)", PRIMARY),
                   ("CNN 추론 forward", ACCENT), ("8구간 확률 argmax", GREEN),
                   ("3그룹 변환", PINK)], y=5.0, fs=12)
    T(ax, 8.0, 3.0, "(0-12)→어린이  (15-43)→어른  (48-100)→어르신", fs=14, color=PRIMARY)
    T(ax, 8.0, 1.3, "연령 CNN: 8개 구간을 3그룹으로", fs=17, color=INK)
    return save(fig, "s2_agecnn")


def sc_agevote():
    fig, ax = fig_ax()
    import numpy as np
    rng = np.random.default_rng(1)
    votes = ["어른"] * 13 + ["어린이"] * 5 + ["어르신"] * 2
    rng.shuffle(votes)
    for i, v in enumerate(votes):
        c = {"어른": GREEN, "어린이": PINK, "어르신": PRIMARY}[v]
        ax.add_patch(Circle((1.6 + (i % 10) * 1.4, 6.2 - (i // 10) * 1.1), 0.42, fc=c, ec="white", lw=2, zorder=3))
    T(ax, 8.0, 4.3, "최근 20프레임 중 13번↑(과반) → '어른' 확정", fs=15, color=GREEN)
    T(ax, 8.0, 3.3, "바꾼 뒤 4초 쿨다운 → 깜빡임 방지", fs=14, color=ACCENT)
    T(ax, 8.0, 1.3, "연령 다수결 + 쿨다운으로 안정", fs=17, color=INK)
    return save(fig, "s2_agevote")


def sc_hyster():
    fig, ax = fig_ax()
    import numpy as np
    xs = np.linspace(1.5, 14.5, 200)
    ratio = 1.05 + 0.25 * np.sin((xs - 1.5) * 1.1)
    ax.plot(xs, 3.4 + ratio, color=PRIMARY, lw=3)
    ax.axhline(3.4 + 1.15, xs.min() / 16, 1, ls="--", color=GREEN, lw=2)
    ax.axhline(3.4 + 0.90, 0, 1, ls="--", color=PINK, lw=2)
    T(ax, 15.2, 3.4 + 1.15, "1.15\n펴짐", fs=12, color=GREEN, ha="left")
    T(ax, 15.2, 3.4 + 0.90, "0.90\n접힘", fs=12, color=PINK, ha="left")
    T(ax, 8.0, 7.6, "손가락 판정: 거리비 + 관절각도 + 이중 임계값", fs=16, color=INK)
    T(ax, 8.0, 2.2, "그 사이(애매)는 '직전 상태 유지' → 깜빡임(플리커) 제거", fs=14, color=ACCENT)
    return save(fig, "s2_hyster")


def sc_posevote():
    fig, ax = fig_ax()
    frames = ["V", "주먹", "주먹", "주먹", "주먹", "주먹"]
    for i, f in enumerate(frames):
        c = PINK if f == "V" else PRIMARY
        rbox(ax, 1.4 + i * 2.35, 4.6, 2.0, 1.5, fc="white", ec=c, lw=2.5)
        T(ax, 2.4 + i * 2.35, 5.35, f, fs=15, color=c)
    arrow(ax, (8.0, 4.2), (8.0, 3.3), color=INK, lw=4)
    rbox(ax, 5.8, 1.9, 4.4, 1.3, fc="#EAF1FF", ec=PRIMARY, lw=3)
    T(ax, 8.0, 2.55, "다수결 → '주먹'!", fs=17, color=PRIMARY)
    T(ax, 8.0, 7.4, "최근 6프레임 손모양 다수결 → 과도기 오발 제거", fs=16, color=INK)
    return save(fig, "s2_posevote")


def sc_oneeuro():
    fig, ax = fig_ax()
    import numpy as np
    xs = np.linspace(0, 6, 240)
    raw = 5.4 + 0.4 * np.sin(xs * 5) + 0.3 * np.sin(xs * 19)
    slow = 5.4 + 0.4 * np.sin(xs * 5)
    ax.plot(1.4 + xs * 2.2, raw, color="#FF7A7A", lw=1.8)
    ax.plot(1.4 + xs * 2.2, slow, color=GREEN, lw=3.5)
    T(ax, 8.0, 7.5, "One-Euro 필터: 속도에 따라 필터 세기를 바꿔요", fs=16, color=INK)
    T(ax, 4.0, 2.8, "느릴 때 → 강하게(덜 떨림)", fs=14, color=GREEN)
    T(ax, 12.0, 2.8, "빠를 때 → 약하게(덜 느림)", fs=14, color=ACCENT)
    mascot(ax, 14.0, 6.6, 0.45)
    return save(fig, "s2_oneeuro")


def sc_clamp():
    fig, ax = fig_ax()
    ax.add_patch(Circle((4.0, 5.0), 0.3, fc=PRIMARY, zorder=3))
    T(ax, 4.0, 4.3, "이전 커서", fs=13)
    ax.add_patch(Circle((12.0, 6.2), 0.3, fc="#FF7A7A", zorder=3))
    T(ax, 12.0, 6.9, "튄 위치(오류)", fs=12, color="#c0392b")
    arrow(ax, (4.3, 5.05), (11.7, 6.15), color="#FF7A7A", lw=2, rad=0.0)
    ax.add_patch(Circle((5.6, 5.2), 0.3, fc=GREEN, zorder=4))
    arrow(ax, (4.3, 5.05), (5.4, 5.18), color=GREEN, lw=4)
    T(ax, 5.9, 4.4, "최대 이동 제한(클램프)", fs=12, color=GREEN)
    T(ax, 8.0, 2.6, "손 크기로 임계 정규화 → 멀든 가깝든 똑같이", fs=14, color=ACCENT)
    T(ax, 8.0, 1.3, "커서 순간이동 방지 + 거리 정규화", fs=16, color=INK)
    return save(fig, "s2_clamp")


def sc_apd():
    fig, ax = fig_ax()
    data = [("에임", "손바닥 중심 커서\nOne-Euro+클램프", PRIMARY, 3.0),
            ("핀치", "엄지끝·검지끝 거리\n6프레임 유지→담기", GREEN, 8.0),
            ("드웰", "2초 머무름\n진행 링 다 차면 선택", ACCENT, 13.0)]
    for name, s, c, x in data:
        rbox(ax, x - 2.3, 3.4, 4.6, 3.2, fc="white", ec=c, lw=3)
        T(ax, x, 5.8, name, fs=18, color=c)
        T(ax, x, 4.5, s, fs=12)
    T(ax, 8.0, 7.6, "에임 + 핀치 + 드웰 (담기 쿨다운 500ms)", fs=17, color=INK)
    T(ax, 8.0, 1.3, "가리키기와 선택을 '분리'해서 오작동 감소", fs=15, color=ACCENT)
    return save(fig, "s2_apd")


def sc_dropfist():
    fig, ax = fig_ax()
    rbox(ax, 1.2, 3.2, 6.6, 3.6, fc="#FFECEC", ec="#e05a5a", lw=3)
    T(ax, 4.5, 6.3, "왜 주먹·엄지척을 뺐나?", fs=15, color="#c0392b")
    T(ax, 4.5, 5.2, "주먹 = 손가락이 가려짐\n(occlusion → 좌표 튐)", fs=13)
    T(ax, 4.5, 3.9, "엄지척 = 엄지가 제일 흔들림", fs=13)
    rbox(ax, 8.4, 3.2, 6.4, 3.6, fc="#EAF7EF", ec=GREEN, lw=3)
    T(ax, 11.6, 6.3, "그래서 바꿈", fs=15, color=GREEN)
    T(ax, 11.6, 5.2, "핀치 = 두 손끝 거리\n(항상 잘 보임)", fs=13)
    T(ax, 11.6, 3.9, "드웰 = 위치 + 시간(포즈 X)", fs=13)
    T(ax, 8.0, 1.3, "'항상 보이는 점의 거리·위치'로 판정 = 안정", fs=16, color=INK)
    return save(fig, "s2_dropfist")


def sc_swipe():
    fig, ax = fig_ax()
    for i in range(4):
        ax.add_patch(Circle((3.5 + i * 2.2, 5.0 + (0.1 if i % 2 else -0.1)), 0.3, fc=PRIMARY, zorder=3))
    arrow(ax, (3.5, 5.0), (10.1, 5.0), color=ACCENT, lw=5)
    T(ax, 6.8, 6.0, "열린 손 + 수평 이동", fs=15, color=ACCENT)
    T(ax, 8.0, 3.4, "쿨다운 800ms로 한 번에 한 칸만", fs=14, color=PRIMARY)
    T(ax, 8.0, 1.3, "스와이프: 카테고리 넘기기", fs=17, color=INK)
    return save(fig, "s2_swipe")


def sc_threads():
    fig, ax = fig_ax()
    rbox(ax, 1.2, 4.4, 6.4, 2.8, fc="#EAF1FF", ec=PRIMARY, lw=3)
    T(ax, 4.4, 6.6, "UI 스레드", fs=15, color=PRIMARY)
    T(ax, 4.4, 5.4, "항상 반응(안 멈춤)", fs=13)
    rbox(ax, 8.4, 4.4, 6.4, 2.8, fc="#FFF1E6", ec=ACCENT, lw=3)
    T(ax, 11.6, 6.6, "Vision 스레드", fs=15, color=ACCENT)
    T(ax, 11.6, 5.4, "무거운 카메라 처리", fs=13)
    arrow(ax, (8.4, 5.0), (7.6, 5.0), color=GREEN, lw=3)
    rbox(ax, 6.2, 3.0, 3.6, 0.9, fc="white", ec=GREEN, lw=2)
    T(ax, 8.0, 3.45, "시그널(큐로 순서대로)", fs=12, color=GREEN)
    T(ax, 8.0, 1.7, "결과만 시그널로 전달 → 위젯 충돌(경쟁조건) 없음", fs=15, color=INK)
    return save(fig, "s2_threads")


def sc_gil():
    fig, ax = fig_ax()
    T(ax, 8.0, 7.6, "GIL: 파이썬은 한 번에 한 스레드만 코드 실행", fs=16, color=INK)
    rbox(ax, 1.4, 3.4, 6.4, 3.0, fc="#FFF7F0", ec=ACCENT, lw=3)
    T(ax, 4.6, 5.9, "순수 파이썬", fs=14, color=ACCENT)
    T(ax, 4.6, 4.7, "동시에 못 돎 (GIL)", fs=13)
    rbox(ax, 8.2, 3.4, 6.4, 3.0, fc="#EFFaf3", ec=GREEN, lw=3)
    T(ax, 11.4, 5.9, "카메라 I/O · OpenCV/MediaPipe", fs=13, color=GREEN)
    T(ax, 11.4, 4.6, "GIL을 '풀어서' 진짜 병행", fs=13)
    T(ax, 8.0, 1.9, "그래서 무거운 비전 처리를 스레드로 떼면 효과 있음", fs=15, color=INK)
    return save(fig, "s2_gil")


def sc_nlu():
    fig, ax = fig_ax()
    boxes_row(ax, [("문장", GRAY), ("키 있으면 GPT", PRIMARY), ("없으면 규칙 파서", ACCENT),
                   ("같은 JSON(OrderIntent)", GREEN), ("장바구니", PINK)], y=5.0, fs=12)
    T(ax, 8.0, 3.0, "OrderIntent: 메뉴·개수·세트·음료·사이즈·사이드", fs=14, color=PRIMARY)
    T(ax, 8.0, 1.3, "자연어 주문: 온라인/오프라인 둘 다 같은 결과", fs=16, color=INK)
    mascot(ax, 1.5, 7.1, 0.45)
    return save(fig, "s2_nlu")


def sc_langdet():
    fig, ax = fig_ax()
    rules = [("한글 있으면", "한국어(ko)", PRIMARY), ("한글 없고 한자 있으면", "중국어(zh)", PINK),
             ("둘 다 없으면", "영어(en)", GREEN)]
    for i, (cond, res, c) in enumerate(rules):
        y = 6.2 - i * 1.5
        rbox(ax, 2.0, y - 0.55, 5.6, 1.1, fc="white", ec=GRAY, lw=2)
        T(ax, 4.8, y, cond, fs=14)
        arrow(ax, (7.7, y), (9.0, y), color=ACCENT, lw=3)
        rbox(ax, 9.2, y - 0.55, 4.6, 1.1, fc="white", ec=c, lw=2.5)
        T(ax, 11.5, y, res, fs=15, color=c)
    T(ax, 8.0, 1.3, "언어를 자동 감지 → 화면도 그 언어로 전환", fs=16, color=INK)
    return save(fig, "s2_langdet")


def sc_dbschema():
    fig, ax = fig_ax()
    rbox(ax, 4.8, 3.2, 6.4, 3.8, fc="white", ec=GREEN, lw=3)
    T(ax, 8.0, 6.5, "orders (주문 통계)", fs=15, color=GREEN)
    for i, c in enumerate(["items 주문내역", "total 금액", "weekday 요일(0-6)", "hour 시간(0-23)"]):
        T(ax, 8.0, 5.6 - i * 0.6, "• " + c, fs=12, ha="center")
    T(ax, 8.0, 2.2, "두 스레드가 함께 써서 Lock으로 안전하게(직렬화)", fs=14, color=ACCENT)
    T(ax, 8.0, 1.1, "SQLite 테이블 (얼굴 정보 없음, 익명 주문 통계만)", fs=16, color=INK)
    return save(fig, "s2_dbschema")


def sc_privacy():
    fig, ax = fig_ax()
    sym_face(ax, 4.5, 5.2, 1.4)
    ax.plot([2.9, 6.1], [3.7, 6.7], color="#FF5B5B", lw=6, zorder=6)
    ax.plot([6.1, 2.9], [3.7, 6.7], color="#FF5B5B", lw=6, zorder=6)
    arrow(ax, (6.8, 5.2), (8.4, 5.2), color=ACCENT, lw=4)
    T(ax, 11.4, 5.6, "얼굴 사진·숫자", fs=15, color="#c0392b")
    T(ax, 11.4, 4.7, "저장 안 함", fs=17, color="#c0392b")
    T(ax, 8.0, 2.9, "카메라는 연령대·손동작만 인식", fs=14, color=GREEN)
    T(ax, 8.0, 1.3, "얼굴 정보를 남기지 않아 개인정보 안전", fs=16, color=INK)
    return save(fig, "s2_privacy")


def sc_states():
    fig, ax = fig_ax()
    steps = [("환영", PRIMARY), ("메뉴", ACCENT), ("완료", GREEN)]
    xs = [3.0, 8.0, 13.0]
    for (n, c), x in zip(steps, xs):
        ax.add_patch(Circle((x, 5.6), 1.0, fc="white", ec=c, lw=4, zorder=3))
        T(ax, x, 5.6, n, fs=17, color=c)
    arrow(ax, (4.1, 5.6), (6.9, 5.6), color=INK, lw=3.5)
    arrow(ax, (9.1, 5.6), (11.9, 5.6), color=INK, lw=3.5)
    arrow(ax, (13.0, 4.5), (3.0, 4.5), color=GRAY, lw=2.5, rad=0.2)
    T(ax, 8.0, 3.3, "90초 무동작 → 처음으로 (세션 리셋)", fs=14, color=GRAY)
    modes = [("표준", PRIMARY), ("실버 x1.5", ACCENT), ("어린이 x1.3", GREEN), ("고대비", INK)]
    for i, (m, c) in enumerate(modes):
        rbox(ax, 1.4 + i * 3.5, 1.5, 3.1, 0.9, fc="white", ec=c, lw=2, rad=0.15)
        T(ax, 2.95 + i * 3.5, 1.95, m, fs=12, color=c)
    T(ax, 8.0, 7.6, "상태머신(3단계) + 자동 4모드", fs=17, color=INK)
    return save(fig, "s2_states")


def sc_access():
    fig, ax = fig_ax()
    items = [("자동 변신", "연령 맞춤 화면", PRIMARY), ("TTS", "음성 안내(듣기)", ACCENT),
             ("STT", "말로 주문(말하기)", GREEN), ("다국어", "한/영/중", PINK)]
    pos = [(4.3, 5.4), (11.7, 5.4), (4.3, 2.6), (11.7, 2.6)]
    for (t, s, c), (x, y) in zip(items, pos):
        rbox(ax, x - 3.0, y - 1.0, 6.0, 2.0, fc="white", ec=c, lw=3)
        T(ax, x - 1.8, y, t, fs=16, color=c)
        T(ax, x + 1.0, y, s, fs=13)
    T(ax, 8.0, 7.9, "접근성(배리어프리) 총정리", fs=18, color=INK)
    return save(fig, "s2_access")


def sc_clahe():
    fig, ax = fig_ax()
    import numpy as np
    rng = np.random.default_rng(0)
    dark = rng.normal(0.3, 0.06, 4000)
    ax.hist(1.4 + dark * 5, bins=30, color="#889", zorder=2)
    T(ax, 3.8, 7.2, "어두움(한쪽 몰림)", fs=13, color=GRAY)
    arrow(ax, (7.4, 5.0), (8.8, 5.0), color=ACCENT, lw=5)
    T(ax, 8.1, 5.7, "CLAHE", fs=14, color=ACCENT)
    even = rng.uniform(0, 1, 4000)
    ax.hist(9.4 + even * 5, bins=30, color=GREEN, zorder=2)
    T(ax, 11.9, 7.2, "고르게 폄(잘 보임)", fs=13, color=GREEN)
    T(ax, 8.0, 1.2, "밝기 보정(히스토그램 평활화)으로 인식률↑", fs=16, color=INK)
    return save(fig, "s2_clahe")


def sc_pipeline():
    fig, ax = fig_ax()
    col_boxes(ax, [("main.py 실행 → 창 표시", GRAY), ("VisionThread 시작", PRIMARY),
                   ("연령 다수결 → 테마 변신", ACCENT),
                   ("주문(에임·핀치·드웰 / 음성)", PINK), ("결제 → 주문번호·DB 저장", PRIMARY),
                   ("완료 → 90초 후 환영", GRAY)], x=8.0, y0=7.0, dy=0.92, w=9.4, h=0.78, fs=13)
    T(ax, 8.0, 0.7, "전체 파이프라인 (앱 시작 → 결제)", fs=16, color=INK)
    return save(fig, "s2_pipeline")


def sc_numbers():
    fig, ax = fig_ax()
    nums = [("468", "얼굴 점"), ("21", "손 점"), ("8→3", "연령 구간→그룹"),
            ("227", "blob 크기"), ("20→13", "연령 다수결"), ("6", "제스처 다수결"),
            ("1.15/0.90", "손가락 임계"), ("500ms", "핀치 쿨다운"), ("2000ms", "드웰 시간"), ("90초", "세션 리셋")]
    cols = [PRIMARY, GREEN, ACCENT, PINK, PRIMARY, GREEN, ACCENT, PINK, PRIMARY, GREEN]
    for i, ((n, s), c) in enumerate(zip(nums, cols)):
        x = 2.2 + (i % 5) * 3.0
        y = 5.6 - (i // 5) * 2.6
        rbox(ax, x - 1.35, y - 0.95, 2.7, 1.9, fc="white", ec=c, lw=2.5)
        T(ax, x, y + 0.25, n, fs=18, color=c)
        T(ax, x, y - 0.55, s, fs=11)
    T(ax, 8.0, 8.0, "외워두면 좋은 핵심 숫자", fs=18, color=INK)
    return save(fig, "s2_numbers")


def sc_wrapup():
    fig, ax = fig_ax()
    mascot(ax, 3.2, 4.6, 1.1, say="원리까지 이해했어!")
    lines = ["Step 2 = '왜·어떻게'를 숫자와 순서로 이해", "임베딩·코사인·평균빼기 / 히스테리시스·다수결·One-Euro",
             "스레드·시그널·GIL / DB·개인정보 / 상태머신·접근성", "", "다음 → Step 3: 실제 코드와 수식으로 더 깊게!"]
    for i, l in enumerate(lines):
        T(ax, 9.6, 6.6 - i * 1.0, l, fs=15 if i < 4 else 16,
          color=INK if i < 4 else ACCENT, ha="center")
    return save(fig, "s2_wrapup")


def sc_end():
    fig, ax = fig_ax("#E3F0DC")
    mascot(ax, 8.0, 4.4, 1.5, say="Step 3에서 또 만나! 화이팅!")
    T(ax, 8.0, 8.0, "Step 2 끝 — 잘 했어요!", fs=26, color=GREEN)
    return save(fig, "s2_end")


SCENE2 = {
    "cover": sc_cover, "welcome": sc_welcome, "arch": sc_arch, "frame": sc_frame,
    "embed": sc_embed, "cosine": sc_cosine, "eucvs": sc_eucvs, "meanface": sc_meanface,
    "regpipe": sc_regpipe, "safety3": sc_safety3, "agecnn": sc_agecnn, "agevote": sc_agevote,
    "hyster": sc_hyster, "posevote": sc_posevote, "oneeuro": sc_oneeuro, "clamp": sc_clamp,
    "apd": sc_apd, "dropfist": sc_dropfist, "swipe": sc_swipe, "threads": sc_threads,
    "gil": sc_gil, "nlu": sc_nlu, "langdet": sc_langdet, "dbschema": sc_dbschema,
    "privacy": sc_privacy, "states": sc_states, "access": sc_access, "clahe": sc_clahe,
    "pipeline": sc_pipeline, "numbers": sc_numbers, "wrapup": sc_wrapup, "end": sc_end,
}

PRES2 = [
    ("cover", None, None, None),
    ("welcome", "Step 2에 온 걸 환영해요", ["Step 1은 '비유'로 이해했어요",
        "Step 2는 '원리·숫자·순서'로 이해해요", "같은 주제를 한 단계 더 깊게"], "비유 → 원리로 레벨업"),
    ("arch", "아키텍처 자세히", ["카메라 처리는 VisionThread(별도 스레드)",
        "결과는 5가지 시그널로 UI에 전달", "age_group·face_present·gesture·frame_ready·status"],
        "스레드 + 시그널 구조"),
    ("frame", "한 프레임 처리 순서", ["좌우반전 → 밝기보정(CLAHE)",
        "얼굴 468점 · 손 21점 추출", "연령은 3프레임마다 1번(무거워서)"], "초당 약 60프레임"),
    ("cosine", "코사인 유사도 (수식 직관)", ["cos θ = a·b / (|a||b|)",
        "정규화하면 내적 한 번으로 계산", "값 -1~1, 1에 가까울수록 닮음"], "방향으로 닮음 재기"),
    ("eucvs", "유클리드 vs 코사인", ["유클리드=직선거리, 크기에 민감",
        "코사인=방향(패턴) 비교, 잡음에 강함", "패턴 비교엔 코사인이 유리"], "왜 코사인을 쓰나"),
    ("agecnn", "연령 CNN 자세히", ["얼굴 잘라 227×227 blob(평균 빼기)",
        "CNN이 8구간 확률 → argmax", "0-12=어린이 / 15-43=어른 / 48+=어르신"], "이미지를 보고 나이 추정"),
    ("agevote", "연령 다수결 + 쿨다운", ["매 프레임은 흔들려요",
        "최근 20 중 13↑(과반)일 때만 전환", "바꾼 뒤 4초는 다시 안 바꿈"], "화면 깜빡임 방지"),
    ("hyster", "손가락 판정 (히스테리시스)", ["거리비 + 관절 각도 함께 봄",
        "펴짐 ≥1.15 / 접힘 ≤0.90", "그 사이는 직전 상태 유지"], "경계 플리커 제거"),
    ("posevote", "손모양 다수결", ["최근 6프레임을 모아 과반으로 확정",
        "주먹 펴는 '과도기' 오발 제거", "연령 다수결과 같은 아이디어"], "튀지 않는 제스처"),
    ("oneeuro", "One-Euro 필터 원리", ["손 속도에 따라 필터 세기 조절",
        "느리면 강하게(덜 떨림)", "빠르면 약하게(덜 느림)"], "지연·떨림 동시에 잡기"),
    ("clamp", "커서 클램프 + 정규화", ["한 프레임 최대 이동 제한(순간이동 방지)",
        "손 크기로 임계 정규화", "→ 카메라 거리와 무관"], "커서를 더 안정적으로"),
    ("apd", "에임 · 핀치 · 드웰 상세", ["에임=손바닥 커서(필터+클램프)",
        "핀치=6프레임 유지→담기(쿨다운 500ms)", "드웰=2초 머무름→진행 링"], "가리키기와 선택을 분리"),
    ("dropfist", "주먹·엄지척을 뺀 이유", ["주먹=손가락 가려짐(occlusion)",
        "엄지척=엄지가 가장 흔들림", "→ 핀치·드웰로 대체(항상 보이는 점)"], "거리·위치 기반이 안정적"),
    ("swipe", "스와이프 판정", ["열린 손 + 수평 이동일 때만",
        "쿨다운 800ms → 한 번에 한 칸", "커서 이동과 구분"], "카테고리 넘기기"),
    ("threads", "멀티스레딩 + 시그널", ["UI는 항상 반응(안 멈춤)",
        "무거운 카메라 처리는 따로", "결과만 시그널(큐로 순서대로)"], "경쟁조건 없이 안전"),
    ("gil", "GIL 자세히", ["파이썬은 한 번에 한 스레드만 실행",
        "하지만 카메라 I/O·C확장은 GIL 해제", "그래서 스레드 분리가 효과 있음"], "스레드가 의미 있는 이유"),
    ("nlu", "자연어 주문 파이프라인", ["키 있으면 GPT, 없으면 규칙 파서",
        "둘 다 같은 JSON(OrderIntent)", "메뉴·개수·세트·음료·사이즈 추출"], "온·오프라인 모두 동작"),
    ("langdet", "언어 감지 규칙", ["한글→ko, 한자→zh, 아니면 en",
        "감지한 언어로 화면 전환", "영어로 말하면 UI도 영어로"], "다국어 자동 전환"),
    ("dbschema", "DB 스키마 (SQLite)", ["orders: 금액·요일·시간(통계)",
        "Lock으로 두 스레드 안전", "얼굴 정보는 저장 안 함"], "익명 주문 통계만"),
    ("privacy", "개인정보 자세히", ["얼굴 사진·숫자 모두 저장 안 함",
        "카메라는 연령대·손동작만 인식", "로컬(매장 안)에만 저장"], "따뜻한 AI의 약속"),
    ("states", "상태머신 + 4모드", ["환영→메뉴→완료(정해진 규칙)",
        "90초 무동작 시 리셋", "표준/실버x1.5/어린이x1.3/고대비"], "화면 흐름과 변신"),
    ("access", "접근성 총정리", ["연령 자동 변신",
        "TTS(듣기) · STT(말하기)", "다국어 지원"], "누구나 쉽게(배리어프리)"),
    ("clahe", "밝기 보정 (과학)", ["어두우면 밝기가 한쪽으로 몰림",
        "CLAHE로 고르게 폄", "→ 어두운 곳에서도 인식률↑"], "히스토그램 평활화"),
    ("pipeline", "전체 파이프라인", ["시작→비전→연령 변신",
        "→ 주문(손·말) → 결제·저장 → 완료", "이 순서로 설명 연습!"], "엔드투엔드 흐름"),
    ("numbers", "핵심 숫자 총정리", ["468·21 / 8→3·227",
        "20→13(연령 다수결) / 6(제스처)", "2000ms·90초"], "숫자로 자신 있게 발표"),
    ("wrapup", "Step 2 정리 & Step 3 예고", ["원리·숫자·순서로 이해 완료!",
        "다음은 실제 코드·수식으로 더 깊게"], "Step 3 준비 완료되면 알려줘요"),
    ("end", None, None, None),
]


def build_presentation():
    prs = Presentation()
    prs.slide_width = Inches(13.333); prs.slide_height = Inches(7.5)
    for key, title, bullets, keyline in PRES2:
        img = SCENE2[key]()
        s = blank(prs)
        if title is None:
            bg(s, "#E3F0DC"); picture(s, img, 0, 0, 13.333); continue
        bg(s, BG)
        band(s, title, GREEN, fs=29)
        picture(s, img, 5.55, 1.45, 7.55)
        textbox(s, 0.45, 1.7, 5.0, 4.2, [{"t": "• " + b, "s": 18} for b in bullets])
        rib = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.4), Inches(6.55),
                                 Inches(12.5), Inches(0.72))
        rib.fill.solid(); rib.fill.fore_color.rgb = RGB("#EAF7EF"); rib.line.color.rgb = RGB(GREEN)
        tf = rib.text_frame; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
        r = p.add_run(); r.text = "🔑 핵심: " + keyline; set_run(r, 18, "#1c6b45", True)
    prs.save("발표용_step2.pptx")
    print("SAVED 발표용_step2.pptx  slides:", len(prs.slides._sldIdLst))


# ══════════════════════════════════════════════
# Step 2 퀴즈 100 (더 자세/응용)
# ══════════════════════════════════════════════
TOPICS2 = [
    ("임베딩·전처리", PRIMARY), ("유사도·단골매칭", GREEN), ("연령 CNN", ACCENT),
    ("제스처 판정", PINK), ("필터·안정화", "#7A5AF8"), ("자연어·음성", "#00A5B5"),
    ("구조·시그널", "#E0455E"), ("스레드·GIL", "#2D6CDF"),
    ("DB·개인정보", "#C08A00"), ("흐름·접근성", "#2BB673"),
]

QUIZ2 = {
 0: [("임베딩을 만들 때 원점으로 삼는 랜드마크는?", ["코끝", "턱", "귀"], "①", "위치 불변을 위해 코(1번)."),
     ("스케일(크기)을 없애려고 무엇으로 나누나?", ["가장 먼 점까지 거리", "평균 밝기", "화면 크기"], "①", "크기 무관 비교."),
     ("완성된 임베딩의 차원(숫자 개수)은?", None, "72", "핵심 24점 × (x,y,z)."),
     ("마지막에 벡터 크기를 1로 만드는 것을?", ["정규화", "압축", "복사"], "①", "방향만 남겨 코사인에 적합."),
     ("임베딩은 원본 사진으로 되돌리기 쉽다.", None, "X", "비가역·익명."),
     ("좌우반전(flip)을 하는 이유는?", ["거울처럼 직관적 조작", "속도", "저장"], "①", "사용자가 자기 손을 거울처럼."),
     ("밝기 보정에 쓰는 기법은?", ["CLAHE(평활화)", "블러", "회전"], "①", "역광·저조도 보정."),
     ("얼굴 랜드마크 개수는?", None, "468", "MediaPipe FaceMesh."),
     ("임베딩에 사진 픽셀이 그대로 들어간다.", None, "X", "좌표(모양)만 사용."),
     ("정규화가 0으로 나누기를 피하는 방법은?", ["크기 0이면 그대로 반환", "1을 더함", "무시"], "①", "안전 처리.")],
 1: [("얼굴 닮음 비교에 주로 쓰는 값은?", ["코사인 유사도", "유클리드 거리", "넓이"], "①", "방향 비교."),
     ("코사인 유사도의 값 범위는?", ["-1~1", "0~100", "1~10"], "①", "1이면 같은 방향."),
     ("정규화된 벡터의 코사인은 무엇으로 계산되나?", ["내적(a·b)", "덧셈", "평균"], "①", "|a||b|=1."),
     ("평균 얼굴을 빼는 이유는?", ["남남도 너무 닮아 보여서", "빨라서", "예뻐서"], "①", "공통 성분 제거."),
     ("평균을 뺀 공간에서 남남의 코사인은 대략?", ["0.3 미만", "0.99", "1.0"], "①", "확실히 구별."),
     ("기준(평균)이 있을 때 단골 임계값은?", None, "0.70", "개인차 공간 임계."),
     ("기준이 아직 없을 때 임계값은?", ["0.999", "0.5", "0.1"], "①", "거의 동일만 인정."),
     ("단골 확정에 필요한 연속 프레임 수는?", None, "8", "우연 일치 방지."),
     ("유클리드 거리는 크기·밝기 잡음에 민감하다.", None, "O", "그래서 코사인 선호."),
     ("best_match는 무엇을 비교하나?", ["평균 뺀 개인차끼리 코사인", "사진끼리", "이름끼리"], "①", "project 후 비교.")],
 2: [("연령 CNN 입력 blob의 크기는?", ["227×227", "64×64", "1024×1024"], "①", "표준 입력 크기."),
     ("blob을 만들 때 무엇을 빼나?", ["학습 때의 BGR 평균", "0", "최댓값"], "①", "입력 정규화."),
     ("CNN이 낸 8구간 중 무엇으로 하나를 고르나?", ["argmax(최댓값)", "평균", "합"], "①", "가장 큰 확률."),
     ("8개 구간을 몇 그룹으로 묶나?", None, "3", "어린이/어른/어르신."),
     ("(15-43) 구간은 어느 그룹?", ["어른", "어린이", "어르신"], "①", "성인 표준."),
     ("연령 추론을 몇 프레임마다 하나?", ["3", "1", "60"], "①", "무거워서 아낌."),
     ("연령 다수결 창과 최소 득표는?", ["20 중 13", "5 중 2", "100 중 10"], "①", "과반 이상."),
     ("모드 전환 후 재전환을 막는 시간은?", ["4초", "0.1초", "1분"], "①", "깜빡임 방지."),
     ("연령 모델 파일이 없으면 앱이 죽는다.", None, "X", "휴리스틱으로 대체."),
     ("나이 정보는 DB에 저장한다.", None, "X", "화면 결정에만 사용.")],
 3: [("손가락 펴짐 판정에 함께 쓰는 두 가지는?", ["거리비 + 관절각도", "색 + 소리", "무게 + 온도"], "①", "강건한 판정."),
     ("히스테리시스에서 '펴짐' 기준 비율은?", ["1.15", "1.0", "0.5"], "①", "상한 임계."),
     ("'접힘' 기준 비율은?", ["0.90", "1.2", "2.0"], "①", "하한 임계."),
     ("두 임계 사이(애매)일 때는?", ["직전 상태 유지", "무조건 펴짐", "무조건 접힘"], "①", "플리커 제거."),
     ("손모양 다수결은 최근 몇 프레임?", None, "6", "과도기 오발 제거."),
     ("핀치는 어느 두 점의 거리로 판정하나?", ["엄지끝·검지끝", "손목·팔꿈치", "새끼·엄지"], "①", "4번·8번."),
     ("주먹이 불안정한 이유는?", ["손가락 가려짐(occlusion)", "너무 밝아서", "소리 때문"], "①", "좌표 튐."),
     ("엄지척이 불안정한 이유는?", ["엄지가 가장 노이즈 큼", "빨라서", "작아서"], "①", "방향 판정 흔들림."),
     ("담기 확정에 필요한 유지 프레임은?", None, "6", "FIST_HOLD_FRAMES."),
     ("드웰 자동선택 시간은?", ["2000ms", "100ms", "10초"], "①", "머무르면 선택.")],
 4: [("One-Euro 필터의 특징은?", ["속도에 따라 세기 조절", "항상 같은 세기", "필터 안 함"], "①", "적응형."),
     ("느리게 움직일 때 필터는?", ["강하게(덜 떨림)", "약하게", "끔"], "①", "떨림 제거."),
     ("빠르게 움직일 때 필터는?", ["약하게(덜 느림)", "강하게", "끔"], "①", "지연 최소."),
     ("고정 창 이동평균의 단점은?", ["지연↔떨림 트레이드오프", "너무 정확", "무료"], "①", "One-Euro가 개선."),
     ("커서 순간이동을 막는 장치는?", ["이동 상한(클램프)", "확대", "회전"], "①", "프레임당 최대 이동."),
     ("임계를 손 크기로 나누는 이유는?", ["카메라 거리와 무관하게", "예뻐서", "느리게"], "①", "정규화."),
     ("다수결이 막는 것은?", ["순간 오발", "배터리 소모", "소음"], "①", "튐 방지."),
     ("담기 전용 쿨다운은?", ["500ms", "5초", "0"], "①", "연속 담기 허용."),
     ("스와이프 쿨다운은?", ["800ms", "50ms", "10초"], "①", "한 번에 한 칸."),
     ("안정화 3종 세트가 아닌 것은?", ["히스테리시스", "다수결", "화면 밝기"], "③", "필터·다수결·히스테리시스.")],
 5: [("말을 글자로 바꾸는 기술은?", ["STT", "TTS", "DNS"], "①", "음성 인식."),
     ("규칙 파서 결과가 담기는 자료구조는?", ["OrderIntent", "그림", "노래"], "①", "주문 의도."),
     ("OrderIntent에 없는 것은?", ["메뉴", "개수/세트", "날씨"], "③", "주문 정보만."),
     ("한글이 있으면 감지 언어는?", None, "한국어", "ko."),
     ("한글 없이 한자만 있으면?", ["중국어", "영어", "일본어"], "①", "zh."),
     ("GPT 호출이 실패하면?", ["규칙 파서로 대체", "종료", "재부팅"], "①", "같은 JSON 반환."),
     ("숫자 표현 '두 개'에서 수량은?", None, "2", "한국어 수사."),
     ("음성 안내(TTS)는 누구에게 특히 도움?", ["시각장애·고령", "개발자만", "아무도"], "①", "접근성."),
     ("영어로 말하면 화면 언어도 바뀔 수 있다.", None, "O", "언어 전환."),
     ("지원하는 세 언어는?", ["한/영/중", "한/일/영", "영/불/독"], "①", "ko/en/zh.")],
 6: [("화면(프론트엔드) 폴더는?", ["ui", "core", "data"], "①", "UI."),
     ("두뇌(백엔드) 폴더는?", ["core", "ui", "tests"], "①", "로직."),
     ("스레드 간 안전 통신 방법은?", ["시그널/슬롯", "전역변수 직접수정", "파일"], "①", "큐 전달."),
     ("설정·임계값이 모인 파일은?", ["config.py", "main.py", "theme.py"], "①", "한곳 관리."),
     ("앱 진입점 파일은?", None, "main", "main.py."),
     ("얼굴·손 분석 파일은?", ["vision.py", "order.py", "i18n.py"], "①", "비전 엔진."),
     ("기능을 클래스로 나눈 설계를?", ["모듈화(OOP)", "복사", "삭제"], "①", "유지보수 쉬움."),
     ("메뉴 카드·커서 부품 파일은?", ["widgets.py", "nlu.py", "database.py"], "①", "UI 부품."),
     ("시그널은 순서대로(큐) 처리되어 안전하다.", None, "O", "QueuedConnection."),
     ("두뇌와 몸을 나누면 한 곳 고쳐도 영향이 적다.", None, "O", "결합도 낮춤.")],
 7: [("한 번에 한 스레드만 파이썬 코드를 도는 규칙은?", ["GIL", "CSS", "API"], "①", "전역 인터프리터 락."),
     ("그래도 병행에 도움이 되는 작업은?", ["카메라 I/O·C확장", "순수 파이썬 반복문", "없음"], "①", "GIL 해제."),
     ("카메라 담당 스레드 이름은?", ["VisionThread", "MainThread", "IOThread"], "①", "비전 스레드."),
     ("다른 스레드가 위젯을 직접 바꾸면?", ["충돌 위험", "더 빠름", "안전"], "①", "그래서 시그널."),
     ("스레드를 나누는 가장 큰 목적은?", ["UI가 안 멈추게", "소리 크게", "색상"], "①", "반응성."),
     ("멀티프로세싱 대신 스레드를 쓴 이유는?", ["프레임·UI 공유가 잦아서", "느려서", "무거워서"], "①", "가볍고 밀결합."),
     ("DB를 두 스레드가 쓸 때 안전장치는?", ["Lock", "삭제", "복사"], "①", "직렬화."),
     ("sqlite 연결에 필요한 옵션은?", ["check_same_thread=False", "readonly", "memory"], "①", "다중 스레드 접근."),
     ("스레드는 요리사 여러 명에 비유된다.", None, "O", "동시에 일하기."),
     ("GIL 때문에 스레드가 전혀 쓸모없다.", None, "X", "I/O·C확장엔 유효.")],
 8: [("단골·통계를 저장하는 DB는?", ["SQLite", "MySQL 서버", "엑셀"], "①", "가벼운 파일 DB."),
     ("regulars 테이블에 저장되지 않는 것은?", ["얼굴 사진", "별명", "임베딩"], "①", "사진 저장 X."),
     ("임베딩은 어떤 형식으로 저장되나?", ["JSON 숫자배열", "PNG", "MP3"], "①", "텍스트 숫자."),
     ("orders 테이블로 알 수 있는 것은?", ["요일·시간대 인기", "혈액형", "키"], "①", "트렌드."),
     ("데이터는 어디에 저장되나?", ["매장 로컬", "인터넷 서버", "SNS"], "①", "프라이버시."),
     ("SQLite가 부적합한 경우는?", ["수백만 동시 웹 사용자", "매장 로컬", "오프라인"], "①", "대규모 웹 아님."),
     ("임베딩만 저장하면 익명성이 있다.", None, "O", "복원 어려움."),
     ("visit_count는 무엇을 세나?", ["방문 횟수", "메뉴 수", "직원 수"], "①", "단골 방문."),
     ("favorite에는 무엇이 들어가나?", ["즐겨찾는 주문", "비밀번호", "주소"], "①", "늘 먹던 걸로."),
     ("개인정보 보호는 우리 작품의 핵심 가치다.", None, "O", "따뜻한 AI.")],
 9: [("화면 상태 순서는?", ["환영→메뉴→완료", "완료→환영", "메뉴만"], "①", "상태머신."),
     ("무동작 세션 리셋 시간은?", None, "90", "초 단위."),
     ("카메라가 없으면?", ["데모 모드로 동작", "종료", "검은 화면"], "①", "견고성."),
     ("실버 모드 글자 배율은?", ["1.5배", "0.5배", "3배"], "①", "고령자 배려."),
     ("어린이 모드 글자 배율은?", ["1.3배", "2배", "0.8배"], "①", "쉬운 화면."),
     ("결제하면 무엇을 저장하나?", ["주문내역·요일·시간", "아무것도", "사진"], "①", "orders."),
     ("접근성 기능이 아닌 것은?", ["TTS", "STT", "광고 배너"], "③", "배리어프리."),
     ("인터넷이 끊겨도 주문 가능한 이유는?", ["규칙 파서", "위성", "전화"], "①", "오프라인."),
     ("우리 작품 한 줄 요약으로 맞는 것은?", ["누구나 쉬운 배리어프리 키오스크", "고사양 게임기", "냉장고"], "①", "핵심."),
     ("상태머신은 정해진 규칙으로 단계가 바뀐다.", None, "O", "FSM.")],
}


def build_quiz():
    prs = Presentation()
    prs.slide_width = Inches(13.333); prs.slide_height = Inches(7.5)
    s = blank(prs); bg(s, "#E3F0DC"); picture(s, sc_cover(), 0, 0, 13.333)
    tb = s.shapes.add_textbox(Inches(0), Inches(0.25), Inches(13.333), Inches(1.1))
    p = tb.text_frame.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = "🎯 STEP 2 퀴즈 100문제"; set_run(r, 32, GREEN, True)
    s = blank(prs); bg(s, BG); band(s, "퀴즈 사용법", ACCENT, fs=30)
    textbox(s, 1.0, 2.0, 11.3, 4.5, [
        {"t": "• 10개 주제 × 10문제 = 총 100문제 (Step 1보다 자세해요)", "s": 22},
        {"t": "• 원리·숫자·이유를 묻는 문제가 많아요.", "s": 22},
        {"t": "• 문제 → 바로 다음 슬라이드에서 정답·해설 확인", "s": 22},
        {"t": "• 유형: O/X · 3지선다(①②③) · 빈칸", "s": 22},
    ], anchor=MSO_ANCHOR.MIDDLE)
    msc = B.mascot_small()
    for ti, (title, color) in enumerate(TOPICS2):
        banner = B.topic_banner(ti + 1, title, color)
        s = blank(prs); bg(s, "#FFFFFF"); picture(s, banner, 0, 2.7, 13.333)
        items = QUIZ2[ti]
        for half in (0, 5):
            grp = items[half:half + 5]
            s = blank(prs); bg(s, BG)
            band(s, f"[{title}] 문제 {half+1}~{half+5}", color, fs=26)
            textbox(s, 0.7, 1.5, 10.6, 5.6, B.q_lines(grp, half + 1))
            picture(s, msc, 11.5, 5.45, 1.5)
            s = blank(prs); bg(s, "#F2FBF5")
            band(s, f"[{title}] 정답 {half+1}~{half+5}", GREEN, fs=26)
            textbox(s, 0.9, 1.7, 10.4, 5.2, B.a_lines(grp, half + 1))
            picture(s, msc, 11.5, 5.45, 1.5)
    prs.save("퀴즈100_step2.pptx")
    print("SAVED 퀴즈100_step2.pptx  slides:", len(prs.slides._sldIdLst))


def main():
    if os.path.isdir(B.ASSET):
        shutil.rmtree(B.ASSET)
    os.makedirs(B.ASSET, exist_ok=True)
    build_presentation()
    build_quiz()


if __name__ == "__main__":
    main()
