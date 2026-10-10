"""
tests/test_full.py — 전체 완전탐색 시뮬레이션 테스트
======================================================
모든 핵심 모듈을 경계값/예외 상황까지 폭넓게 검증합니다.
  · 수학 유틸 (거리/유사도/필터/조명보정)
  · 메뉴 데이터 무결성
  · 장바구니 OOP (병합/수량/세트/사이즈)
  · 자연어 주문 NLU (수량 추출·세트·다국어(한·영·중)·결제/비우기)
  · 데이터베이스 (주문 통계)
  · 다국어 사전 (키 동등성)
  · 테마 (모든 모드)
  · 제스처 인식기 (주먹/펼침/포인팅/엄지척/스와이프)
  · 연령 추정 휴리스틱
  · GUI 통합 (오프스크린): 모드전환·고대비 버튼·장바구니·제스처·음성주문(소리 안내)·결제

실행:
    python tests/test_full.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# GUI 테스트를 위해 화면 없이(offscreen) 동작하도록 설정
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np

import config
# 테스트 중 카메라/소리를 끔
config.VISION_ENABLED = False
config.TTS_ENABLED = False
import core.speech as _speech_mod
_speech_mod.TTS_ENABLED = False

from core import menu_data
from core.mathutils import (euclidean_distance, cosine_similarity,
                            MovingAverageFilter, normalize_vector,
                            equalize_lighting)
from core.order import Cart, CartLine
from core.nlu import parse_order, detect_language
from core.i18n import TEXTS, Translator
from core import vision as vision_mod
from ui import theme as theme_mod


# ══════════════════════════════════════════════
# 합성(가짜) 랜드마크 도우미
# ══════════════════════════════════════════════
class _LM:
    __slots__ = ("x", "y", "z")
    def __init__(self, x=0.5, y=0.5, z=0.0):
        self.x, self.y, self.z = x, y, z


class _Hand:
    def __init__(self, lms):
        self.landmark = lms


def make_landmarks(n, overrides=None):
    lms = [_LM() for _ in range(n)]
    if overrides:
        for idx, (x, y) in overrides.items():
            lms[idx].x = x
            lms[idx].y = y
    return lms


def make_hand(overrides):
    return _Hand(make_landmarks(21, overrides))


# 손가락 상태별 합성 좌표(현실적인 손 기하: 손목=기준, 손가락은 위로 뻗음)
#   펴짐  = 손끝(tip)이 손목에서 멀리(위로)         접힘 = 손끝이 손바닥쪽(아래)으로 말림
def hand_with(thumb, index, middle, ring, pinky, palm=(0.5, 0.5)):
    """현실적인 손 랜드마크를 만든다. palm 으로 손 전체를 평행 이동(스와이프 테스트)."""
    px, py = palm
    lms = [_LM(px, py) for _ in range(21)]

    def put(i, dx, dy):
        lms[i].x, lms[i].y = px + dx, py + dy

    put(0, 0.0, 0.0)                                   # 손목(기준)
    # 엄지(검지쪽으로 비스듬히): 펴짐이면 옆+위로 크게, 접힘이면 손바닥 안쪽으로
    put(1, -0.06, -0.04); put(2, -0.10, -0.09); put(3, -0.15, -0.14)
    if thumb:
        put(4, -0.24, -0.20)
    else:
        put(4, -0.05, -0.10)
    # 검지~새끼: (mcp, pip, dip, tip, 가로오프셋)
    for on, mcp, pip, dip, tip, ox in [
            (index, 5, 6, 7, 8, -0.05),
            (middle, 9, 10, 11, 12, 0.0),
            (ring, 13, 14, 15, 16, 0.05),
            (pinky, 17, 18, 19, 20, 0.09)]:
        put(mcp, ox, -0.26)
        put(pip, ox, -0.40)
        put(dip, ox, -0.48)
        put(tip, ox, -0.60 if on else -0.18)           # 펴짐=위로 멀리, 접힘=가까이
    return _Hand(lms)


# ══════════════════════════════════════════════
# 1) 수학 유틸
# ══════════════════════════════════════════════
def test_euclidean_basic():
    assert abs(euclidean_distance([0, 0], [3, 4]) - 5.0) < 1e-9
    assert euclidean_distance([1, 1, 1], [1, 1, 1]) == 0.0


def test_cosine_edge():
    assert abs(cosine_similarity([1, 2, 3], [1, 2, 3]) - 1.0) < 1e-9
    assert abs(cosine_similarity([1, 0], [0, 1])) < 1e-9
    assert abs(cosine_similarity([1, 0], [-1, 0]) + 1.0) < 1e-9
    assert cosine_similarity([0, 0], [1, 2]) == 0.0      # 0벡터 → 0(예외)


def test_normalize_vector():
    v = normalize_vector([3, 4])
    assert abs(np.linalg.norm(v) - 1.0) < 1e-9
    z = normalize_vector([0, 0, 0])                       # 0벡터 안전
    assert np.allclose(z, [0, 0, 0])


def test_moving_average():
    maf = MovingAverageFilter(window=3)
    assert maf.update(0, 0) == (0.0, 0.0)
    assert maf.update(10, 10) == (5.0, 5.0)
    assert maf.update(20, 20) == (10.0, 10.0)
    maf.reset()
    assert maf.update(7, 7) == (7.0, 7.0)
    one = MovingAverageFilter(window=1)                   # 창=1 경계
    assert one.update(5, 9) == (5.0, 9.0)
    assert one.update(2, 2) == (2.0, 2.0)


def test_equalize_lighting():
    img = (np.random.default_rng(0).random((40, 40)) * 255).astype(np.uint8)
    out = equalize_lighting(img)
    assert out.shape == img.shape


# ══════════════════════════════════════════════
# 2) 메뉴 데이터 무결성
# ══════════════════════════════════════════════
def test_menu_integrity():
    assert len(menu_data.MENU) >= 10
    ids = [m.item_id for m in menu_data.MENU]
    assert len(ids) == len(set(ids))                      # 아이디 중복 없음
    for m in menu_data.MENU:
        assert m.price > 0
        assert m.category in menu_data.CATEGORY_ORDER
        assert m.name_ko and m.name_en and m.emoji
        assert m.keywords                                  # 키워드 비어있지 않음
    assert len(menu_data.best_sellers()) >= 4
    assert menu_data.get_item("does_not_exist") is None
    for cat in menu_data.CATEGORY_ORDER:
        assert menu_data.items_in_category(cat)            # 카테고리별 1개 이상


# ══════════════════════════════════════════════
# 3) 장바구니 OOP
# ══════════════════════════════════════════════
def test_cart_merge_and_separate():
    cart = Cart()
    fries = menu_data.get_item("side_fries")
    cart.add(fries, qty=1)
    cart.add(fries, qty=2)
    assert len(cart.lines) == 1 and cart.lines[0].qty == 3   # 같은 옵션 병합
    burger = menu_data.get_item("burger_bulgogi")
    cart.add(burger, qty=1, is_set=False)
    cart.add(burger, qty=1, is_set=True)
    burger_lines = [l for l in cart.lines if l.item.item_id == "burger_bulgogi"]
    assert len(burger_lines) == 2                            # 세트 여부 다르면 분리


def test_cart_pricing():
    cart = Cart()
    bulgogi = menu_data.get_item("burger_bulgogi")           # 5500
    cart.add(bulgogi, qty=2, is_set=True, drink_size="L")
    unit = 5500 + menu_data.SET_EXTRA_PRICE + menu_data.SIZE_EXTRA_PRICE["L"]
    assert cart.lines[0].unit_price() == unit
    assert cart.total() == unit * 2
    assert cart.item_count() == 2


def test_cart_change_qty_and_remove():
    cart = Cart()
    cola = menu_data.get_item("drink_cola")
    cart.add(cola, qty=2)
    cart.change_qty(0, +1)
    assert cart.lines[0].qty == 3
    cart.change_qty(0, -3)                                   # 0 이하 → 삭제
    assert cart.is_empty()
    cart.remove_index(99)                                    # 범위 밖 → 무시(예외X)
    cart.add(cola)
    cart.remove_index(0)
    assert cart.is_empty()


def test_cart_records_and_describe():
    cart = Cart()
    cart.add(menu_data.get_item("drink_cola"), drink_size="L")
    recs = cart.to_records()
    assert recs[0]["id"] == "drink_cola" and recs[0]["qty"] == 1
    line = cart.lines[0]
    assert "라지" in line.describe("ko") or "Large" in line.describe("en")


def test_cart_plain_item_no_size_surcharge():
    # 단품(세트X) 비음료에 'L'이 들어와도 사이즈 추가요금이 붙으면 안 됨
    cart = Cart()
    cart.add(menu_data.get_item("burger_bulgogi"), is_set=False, drink_size="L")
    assert cart.lines[0].unit_price() == 5500
    # 음료 단품은 L 추가요금 정상 적용
    cart2 = Cart()
    cart2.add(menu_data.get_item("drink_cola"), drink_size="L")
    assert cart2.lines[0].unit_price() == 2000 + menu_data.SIZE_EXTRA_PRICE["L"]


def test_cart_set_customization_single_line():
    # 세트 음료/사이드 '종류 변경'은 한 줄로, 이중 청구 없이 세트 정가
    cart = Cart()
    cart.add(menu_data.get_item("burger_bulgogi"), is_set=True, drink_size="L",
             drink_id="drink_cola", side_id="side_cheese_stick")
    assert len(cart.lines) == 1
    expected = 5500 + menu_data.SET_EXTRA_PRICE + menu_data.SIZE_EXTRA_PRICE["L"]
    assert cart.total() == expected            # 8700, 콜라/치즈스틱 추가청구 없음
    desc = cart.lines[0].describe("ko")
    assert "콜라" in desc and "치즈스틱" in desc  # 선택 옵션은 표기됨
    # 옵션이 다른 두 세트는 합쳐지지 않음
    cart.add(menu_data.get_item("burger_bulgogi"), is_set=True, drink_size="L",
             drink_id="drink_cider", side_id="side_cheese_stick")
    assert len(cart.lines) == 2



# ══════════════════════════════════════════════
# 4) 자연어 주문 NLU (수량 정확도 포함)
# ══════════════════════════════════════════════
def test_nlu_language():
    assert detect_language("불고기버거 주세요") == "ko"
    assert detect_language("one cola please") == "en"


def test_nlu_complex_korean():
    r = parse_order("불고기버거 세트 하나 주시는데 음료는 콜라 라지로 바꾸고 "
                    "사이드는 치즈스틱으로 바꿀게요")
    m = r.intents[0]
    assert m.item_id == "burger_bulgogi" and m.is_set
    assert m.drink_id == "drink_cola" and m.drink_size == "L"
    assert m.side_id == "side_cheese_stick"


def test_nlu_qty_set_without_number():
    # '세트'의 '세'를 숫자 3으로 오인하면 안 됨 → 수량 1
    r = parse_order("불고기버거 세트 주세요")
    assert r.intents[0].item_id == "burger_bulgogi"
    assert r.intents[0].qty == 1
    assert r.intents[0].is_set is True


def test_nlu_qty_hanwoo():
    # '한우'의 '한'을 숫자 1로 오인하면 안 됨 → '두 개'=2
    r = parse_order("한우버거 두 개 주세요")
    hb = [it for it in r.intents if it.item_id == "burger_hanwoo"][0]
    assert hb.qty == 2


def test_nlu_qty_no_contamination():
    # 버거 수량(2)이 음료 수량으로 새지 않아야 함 → 콜라 1
    r = parse_order("더블 치즈버거 두개랑 콜라 주세요")
    by = {it.item_id: it for it in r.intents}
    assert by["burger_double_cheese"].qty == 2
    assert by["drink_cola"].qty == 1


def test_nlu_korean_number_words():
    assert parse_order("불고기버거 세 개 주세요").intents[0].qty == 3
    assert parse_order("새우버거 다섯 개 주세요").intents[0].qty == 5
    assert parse_order("빅버거 하나 주세요").intents[0].qty == 1


def test_nlu_digit_qty():
    assert parse_order("불고기버거 3개 주세요").intents[0].qty == 3


def test_nlu_english_qty():
    r = parse_order("Two double cheeseburgers and french fries please")
    by = {it.item_id: it for it in r.intents}
    assert by["burger_double_cheese"].qty == 2
    assert "side_fries" in by


def test_nlu_english_set():
    r = parse_order("I want a shrimp burger set and a large cola")
    assert r.detected_language == "en"
    assert r.intents[0].item_id == "burger_shrimp" and r.intents[0].is_set


def test_nlu_clear_and_checkout():
    assert parse_order("전부 삭제해줘").intents[0].action == "clear"
    actions = [it.action for it in parse_order("결제할게요").intents]
    assert "checkout" in actions


def test_nlu_empty():
    assert parse_order("").intents == []
    assert parse_order("   ").intents == []
    assert parse_order("아무 의미 없는 문장").intents == []   # 메뉴 없음 → 빈 결과


def test_nlu_chinese_menu_and_qty():
    # 중국어: 수량이 메뉴 '앞'에 옴("两个"=2). 芝士(치즈) 키워드 오타 회귀 방지
    r = parse_order("两个双层芝士汉堡和薯条")
    assert r.detected_language == "zh"
    by = {it.item_id: it for it in r.intents}
    assert by["burger_double_cheese"].qty == 2
    assert by["side_fries"].qty == 1                      # 수량 전염 없음
    r2 = parse_order("一份鲜虾汉堡套餐，配菜换成芝士棒")
    assert r2.intents[0].item_id == "burger_shrimp" and r2.intents[0].is_set
    assert r2.intents[0].side_id == "side_cheese_stick"
    r3 = parse_order("来一份烤肉汉堡套餐，可乐换成大杯")
    m = r3.intents[0]
    assert m.item_id == "burger_bulgogi" and m.qty == 1 and m.is_set
    assert m.drink_id == "drink_cola" and m.drink_size == "L"


def test_voice_dialog_examples_all_parse():
    # 음성 주문 창의 예시 문장(3개 언어)은 모두 메뉴를 담을 수 있어야 함
    from ui.voice_dialog import VoiceOrderDialog
    for lang, exs in (("ko", VoiceOrderDialog.EXAMPLES_KO),
                      ("en", VoiceOrderDialog.EXAMPLES_EN),
                      ("zh", VoiceOrderDialog.EXAMPLES_ZH)):
        for ex in exs:
            r = parse_order(ex)
            assert r.detected_language == lang, ex
            assert any(it.item_id for it in r.intents), ex


# ══════════════════════════════════════════════
# 5) 데이터베이스 (주문 통계)
# ══════════════════════════════════════════════
def _fresh_db():
    from core.database import KioskDatabase
    p = config.DATA_DIR / "_pytest_full.db"
    if p.exists():
        os.remove(p)
    return KioskDatabase(p), p


def test_db_order_stats():
    db, p = _fresh_db()
    try:
        db.record_order([{"id": "drink_cola", "name": "콜라", "qty": 2}], 4000)
        db.record_order([{"id": "side_fries", "name": "감자튀김", "qty": 1}], 2500)
        s = db.sales_summary()
        assert s["order_count"] == 2
        assert s["total_revenue"] == 6500
        assert s["by_item"].get("콜라") == 2
    finally:
        db.close()
        if p.exists():
            os.remove(p)


# ══════════════════════════════════════════════
# 6) 다국어 / 테마
# ══════════════════════════════════════════════
def test_i18n_key_parity():
    ko, en, zh = set(TEXTS["ko"]), set(TEXTS["en"]), set(TEXTS["zh"])
    assert ko == en, f"누락 키(en): {ko ^ en}"
    assert ko == zh, f"누락 키(zh): {ko ^ zh}"
    tr = Translator("ko")
    assert tr.t("checkout")
    tr.set_lang("en")
    assert tr.t("checkout")
    tr.set_lang("zh")
    assert tr.t("checkout")
    assert tr.t("nonexistent_key") == "nonexistent_key"      # 폴백


def test_theme_all_modes():
    for mode in (config.MODE_STANDARD, config.MODE_SILVER,
                 config.MODE_CHILD, config.MODE_HIGH_CONTRAST):
        th = theme_mod.get_theme(mode)
        css = theme_mod.get_stylesheet(th)
        assert isinstance(css, str) and "QWidget" in css
        assert th.pt(16) >= 9
    # 실버 모드는 글자가 더 큼
    assert (theme_mod.get_theme(config.MODE_SILVER).pt(16)
            > theme_mod.get_theme(config.MODE_STANDARD).pt(16))


# ══════════════════════════════════════════════
# 7) 제스처 인식기
# ══════════════════════════════════════════════
def test_gesture_fist():
    gr = vision_mod.GestureRecognizer()
    hand = hand_with(False, False, False, False, False)
    name = None
    for _ in range(config.FIST_HOLD_FRAMES):
        name, _pos = gr.classify(hand)
    assert name == "fist"


def test_gesture_pinch():
    # 엄지 끝을 검지 끝에 맞댄 '집게 손'을 잠깐 유지하면 pinch(선택)로 확정
    gr = vision_mod.GestureRecognizer()
    hand = hand_with(False, True, False, False, False)
    tip = hand.landmark[8]
    hand.landmark[4].x, hand.landmark[4].y = tip.x + 0.01, tip.y + 0.01
    names = [gr.classify(hand)[0] for _ in range(config.FIST_HOLD_FRAMES)]
    assert names[0] == "pinch_hold"                         # 첫 프레임엔 확정 금지
    assert names[-1] == "pinch"


def test_gesture_open_palm():
    gr = vision_mod.GestureRecognizer()
    name, _ = gr.classify(hand_with(True, True, True, True, True))
    assert name in ("open_palm", "swipe_left", "swipe_right")


def test_gesture_signs():
    gr = vision_mod.GestureRecognizer()
    name = None
    for _ in range(config.FIST_HOLD_FRAMES):                  # 엄지척도 잠깐 유지해야 확정
        name = gr.classify(hand_with(True, False, False, False, False))[0]
    assert name == "sign_yes"
    gr2 = vision_mod.GestureRecognizer()
    assert gr2.classify(hand_with(False, True, True, False, False))[0] == "sign_two"
    gr3 = vision_mod.GestureRecognizer()
    assert gr3.classify(hand_with(False, True, False, False, False))[0] == "point"


def test_gesture_swipe_vertical():
    # 손바닥을 위/아래로 빠르게 휘두르면 swipe_up / swipe_down (목록 넘기기)
    def real_hand_y(py, scale=0.10):
        px = 0.5
        lms = [_LM(px, py) for _ in range(21)]
        lms[9] = _LM(px, py - scale)
        for mcp, pip, tip, ox in [(5, 6, 8, -0.02), (9, 10, 12, 0.0),
                                  (13, 14, 16, 0.02), (17, 18, 20, 0.035)]:
            lms[mcp] = _LM(px + ox, py - scale)
            lms[pip] = _LM(px + ox, py - scale * 1.6)
            lms[tip] = _LM(px + ox, py - scale * 2.4)
        lms[3] = _LM(px - 0.06, py - scale * 0.6)
        lms[4] = _LM(px - 0.10, py - scale)
        return _Hand(lms)

    clock = [1000.0]
    orig_time = vision_mod.time.time
    vision_mod.time.time = lambda: (clock.__setitem__(0, clock[0] + 0.05) or clock[0])
    try:
        gr = vision_mod.GestureRecognizer()
        up = [gr.classify(real_hand_y(p))[0] for p in (0.9, 0.7, 0.5, 0.3)]
        assert "swipe_up" in up, up
        gr2 = vision_mod.GestureRecognizer()
        down = [gr2.classify(real_hand_y(p))[0] for p in (0.3, 0.5, 0.7, 0.9)]
        assert "swipe_down" in down, down
        assert not any(n in ("swipe_left", "swipe_right") for n in up + down)
    finally:
        vision_mod.time.time = orig_time


def test_gesture_swipe():
    # 새 파이프라인은 손바닥을 '빠르게'(프레임당 큰 이동) 휘두를 때만 스와이프로 확정한다
    # (느린 이동=커서/open_palm). One-Euro 필터가 프레임 간 시간에 의존하므로, 시간을
    # 실제 카메라(약 20fps)처럼 진행시키고 실제 손 크기(hand_scale≈0.10)로 재현한다.
    def real_hand(px, scale=0.10):
        lms = [_LM(px, 0.5) for _ in range(21)]
        lms[9] = _LM(px, 0.5 - scale)                 # 중지뿌리 → hand_scale
        for mcp, pip, tip, ox in [(5, 6, 8, -0.02), (9, 10, 12, 0.0),
                                  (13, 14, 16, 0.02), (17, 18, 20, 0.035)]:
            lms[mcp] = _LM(px + ox, 0.5 - scale)
            lms[pip] = _LM(px + ox, 0.5 - scale * 1.6)
            lms[tip] = _LM(px + ox, 0.5 - scale * 2.4)
        lms[3] = _LM(px - 0.06, 0.5 - scale * 0.6)
        lms[4] = _LM(px - 0.10, 0.5 - scale)          # 엄지 편 상태
        return _Hand(lms)

    clock = [1000.0]
    orig_time = vision_mod.time.time
    vision_mod.time.time = lambda: (clock.__setitem__(0, clock[0] + 0.05) or clock[0])
    try:
        gr = vision_mod.GestureRecognizer()
        right = [gr.classify(real_hand(p))[0] for p in (0.2, 0.45, 0.7, 0.9)]
        assert "swipe_right" in right, right
        clock[0] = 1000.0
        gl = vision_mod.GestureRecognizer()
        left = [gl.classify(real_hand(p))[0] for p in (0.9, 0.65, 0.4, 0.15)]
        assert "swipe_left" in left, left
    finally:
        vision_mod.time.time = orig_time


# ══════════════════════════════════════════════
# 8) 연령 추정(기하 휴리스틱 대체 경로)
# ══════════════════════════════════════════════
def test_estimate_age_group():
    def face(eye, fh):
        # 눈 사이=eye, 얼굴세로=fh 가 되도록 좌표 구성
        ov = {33: (0.5 - eye / 2, 0.5), 263: (0.5 + eye / 2, 0.5),
              10: (0.5, 0.5 - fh / 2), 152: (0.5, 0.5 + fh / 2)}
        return make_landmarks(478, ov)
    assert vision_mod.estimate_age_group(face(0.20, 0.30), 480) == "child"    # 0.667
    assert vision_mod.estimate_age_group(face(0.165, 0.30), 480) == "adult"   # 0.55
    assert vision_mod.estimate_age_group(face(0.14, 0.30), 480) == "senior"   # 0.467


# ══════════════════════════════════════════════
# 9) GUI 통합 (오프스크린)
# ══════════════════════════════════════════════
_APP = None
def _get_app():
    global _APP
    from PyQt6.QtWidgets import QApplication
    _APP = QApplication.instance() or QApplication(sys.argv)
    return _APP


def _make_window():
    _get_app()
    from ui.main_window import KioskMainWindow, SCREEN_MENU, SCREEN_WELCOME, SCREEN_DONE
    return KioskMainWindow(), (SCREEN_WELCOME, SCREEN_MENU, SCREEN_DONE)


def test_gui_modes_and_navigation():
    w, (WEL, MENU, DONE) = _make_window()
    try:
        for mode in (config.MODE_SILVER, config.MODE_CHILD,
                     config.MODE_HIGH_CONTRAST, config.MODE_STANDARD):
            w._manual_set_mode(mode)
            assert w.mode == mode
        w._go_menu()
        assert w.stack.currentIndex() == MENU
        start = w.current_category
        w._handle_gesture_action("swipe_right")
        assert w.current_category != start                    # 카테고리 이동
        w._handle_gesture_action("swipe_left")
        assert w.current_category == start
    finally:
        w.close()


def test_gui_cart_and_checkout():
    w, (WEL, MENU, DONE) = _make_window()
    try:
        w._go_menu()
        w._add_to_cart(menu_data.get_item("burger_bulgogi"))
        assert w.cart.item_count() == 1
        w._handle_gesture_action("pinch")                     # 집게 손 → 베스트 버거 담기
        assert w.cart.item_count() == 2
        w._checkout()
        assert w.stack.currentIndex() == DONE                 # 결제 완료 화면
        # 빈 장바구니 결제는 완료화면으로 가지 않음
        w2, (_, _, D2) = _make_window()
        w2._go_menu()
        w2._checkout()
        assert w2.stack.currentIndex() != D2
        w2.close()
    finally:
        w.close()


def test_gui_voice_order_flow():
    w, (WEL, MENU, DONE) = _make_window()
    try:
        w.tr.set_lang("ko")
        w._go_menu()
        w._process_order_text("더블 치즈버거 두개랑 콜라 주세요")
        by = {l.item.item_id: l for l in w.cart.lines}
        assert by["burger_double_cheese"].qty == 2
        assert by["drink_cola"].qty == 1                      # 오염 없음
        w._clear_cart()
        assert w.cart.is_empty()
        # 세트+옵션 교체
        w._process_order_text("불고기버거 세트 주세요")
        bset = [l for l in w.cart.lines if l.item.item_id == "burger_bulgogi"][0]
        assert bset.is_set and bset.qty == 1
    finally:
        w.close()


def test_gui_set_override_no_double_charge():
    # 음성 세트 옵션변경이 한 줄·정가로 반영되는지(이중청구 금지) 통합 검증
    w, (WEL, MENU, DONE) = _make_window()
    try:
        w.tr.set_lang("ko")
        w._go_menu()
        w._process_order_text("불고기버거 세트 하나 주시는데 음료는 콜라 라지로 "
                              "바꾸고 사이드는 치즈스틱으로 바꿀게요")
        assert len(w.cart.lines) == 1
        expected = 5500 + menu_data.SET_EXTRA_PRICE + menu_data.SIZE_EXTRA_PRICE["L"]
        assert w.cart.total() == expected            # 8700원 (14200 아님)
    finally:
        w.close()


def test_gui_language_switch_by_voice():
    w, (WEL, MENU, DONE) = _make_window()
    try:
        w.tr.set_lang("ko")
        w._go_menu()
        w._process_order_text("I want a shrimp burger set")
        assert w.tr.lang == "en"                              # 영어로 자동 전환
    finally:
        w.close()


def test_gui_gesture_toggle():
    # 손동작을 끄면 제스처가 무시되고, 켜면 다시 동작해야 함
    w, (WEL, MENU, DONE) = _make_window()
    try:
        w._go_menu()
        start = w.current_category
        w.gesture_btn.setChecked(False)
        w._toggle_gesture()
        assert w._gesture_enabled is False
        w._on_gesture("swipe_right", 0.5, 0.5)
        assert w.current_category == start            # 꺼짐 → 변화 없음
        w.gesture_btn.setChecked(True)
        w._toggle_gesture()
        w._on_gesture("swipe_right", 0.5, 0.5)
        assert w.current_category != start            # 켜짐 → 카테고리 이동
    finally:
        w.close()


def test_gui_gesture_cooldown_and_busy():
    w, (WEL, MENU, DONE) = _make_window()
    try:
        w._go_menu()
        cats = menu_data.CATEGORY_ORDER
        w._select_category(cats[0])
        w._last_gesture_action_ms = 0.0
        w._on_gesture("swipe_right", 0.5, 0.5)
        after_first = w.current_category
        assert after_first != cats[0]                 # 첫 동작 적용
        w._on_gesture("swipe_right", 0.5, 0.5)        # 쿨다운 내 → 무시
        assert w.current_category == after_first
        # 처리 중(_busy)에는 제스처가 무시되어야 함
        w._busy = True
        w._last_gesture_action_ms = 0.0
        before = w.current_category
        w._on_gesture("swipe_right", 0.5, 0.5)
        assert w.current_category == before
        w._busy = False
    finally:
        w.close()


def test_gui_fist_adds_item_under_cursor():
    # 주먹 제스처는 '커서가 가리키는 카드'의 제품을 담아야 함(보고된 버그)
    from ui.widgets import MenuCard
    w, (WEL, MENU, DONE) = _make_window()
    try:
        w.resize(1080, 1920)
        w.show()
        app = _get_app()
        app.processEvents()
        w._go_menu()
        app.processEvents()
        central = w.centralWidget()
        target_card = w.menu_grid.itemAt(0).widget()      # 좌상단 카드(항상 보임)
        assert isinstance(target_card, MenuCard)
        center = target_card.mapTo(central, target_card.rect().center())
        w._cursor_nx = center.x() / max(1, central.width())
        w._cursor_ny = center.y() / max(1, central.height())
        w.cursor.show()
        assert w._menu_item_under_cursor() is target_card.item   # 좌표→카드 매핑
        before = w.cart.item_count()
        w._handle_gesture_action("pinch")
        ids = [l.item.item_id for l in w.cart.lines]
        assert target_card.item.item_id in ids            # 가리킨 제품이 담김
        assert w.cart.item_count() == before + 1
    finally:
        w.close()


def test_gui_fist_fallback_best_without_cursor():
    # 커서가 없을 때(시연 버튼 등)는 현재 카테고리 베스트 메뉴로 담기
    w, (WEL, MENU, DONE) = _make_window()
    try:
        w._go_menu()
        w._menu_item_under_cursor = lambda: None
        w.cursor.hide()
        before = w.cart.item_count()
        w._handle_gesture_action("pinch")
        items = menu_data.items_in_category(w.current_category)
        best = next((m for m in items if m.is_best), items[0])
        ids = [l.item.item_id for l in w.cart.lines]
        assert best.item_id in ids                        # 베스트로 폴백
        assert w.cart.item_count() == before + 1
    finally:
        w.close()


def test_gui_fist_hint_when_cursor_off_card():
    # 커서는 보이지만 메뉴 카드 위가 아니면 아무것도 담지 않고 안내만
    w, (WEL, MENU, DONE) = _make_window()
    try:
        w._go_menu()
        w._clickable_under_cursor = lambda: None          # 커서가 빈 곳(버튼 아님)을 가리킴
        w.cursor.show()
        before = w.cart.item_count()
        w._handle_gesture_action("pinch")
        assert w.cart.item_count() == before              # 변화 없음(안내만)
    finally:
        w.close()


def test_gui_only_pinch_selects():
    # 선택은 집게 손만: 주먹·엄지척으로는 담기지 않아야 함(기본 설정)
    w, (WEL, MENU, DONE) = _make_window()
    try:
        w._go_menu()
        w._menu_item_under_cursor = lambda: None
        w.cursor.hide()
        before = w.cart.item_count()
        w._handle_gesture_action("fist")
        w._handle_gesture_action("sign_yes")
        assert w.cart.item_count() == before
        w._handle_gesture_action("pinch")
        assert w.cart.item_count() == before + 1
    finally:
        w.close()


def test_gui_pinch_clicks_any_button():
    # 집게 손은 커서 아래의 어떤 버튼이든 누름: 카테고리 탭, 장바구니 +, 결제하기
    # (손동작 켜기/끄기 버튼은 손동작으로 끌 수 없게 제외)
    w, (WEL, MENU, DONE) = _make_window()
    app = _get_app()
    try:
        w.resize(1080, 1920)
        w.show()
        w._go_menu()
        for _ in range(5):
            app.processEvents()
        central = w.centralWidget()

        def aim_at(widget):
            c = widget.mapTo(central, widget.rect().center())
            w._cursor_nx = c.x() / central.width()
            w._cursor_ny = c.y() / central.height()
            w.cursor.show()

        # 1) 카테고리 탭
        aim_at(w.cat_buttons[menu_data.CATEGORY_SIDE])
        w._handle_gesture_action("pinch")
        assert w.current_category == menu_data.CATEGORY_SIDE
        # 2) 장바구니 + 버튼
        w._add_to_cart(menu_data.get_item("burger_bulgogi"))
        for _ in range(5):
            app.processEvents()
        plus = next(b for b in w.cart_host.findChildren(type(w.voice_btn))
                    if b.isVisible() and b.text().strip() in ("+", "＋"))
        aim_at(plus)
        before = w.cart.item_count()
        w._handle_gesture_action("pinch")
        assert w.cart.item_count() == before + 1
        # 3) 손동작 켜기/끄기 버튼은 집게로 눌리지 않음
        aim_at(w.gesture_btn)
        w._handle_gesture_action("pinch")
        assert w._gesture_enabled is True
        # 4) 결제하기 버튼
        aim_at(w.checkout_btn)
        w._handle_gesture_action("pinch")
        assert w.stack.currentIndex() == DONE
    finally:
        w.close()


def test_gui_pinch_snaps_to_near_button():
    # 집게로 버튼을 살짝 빗나가도 가까운 버튼을 누름(장바구니 +).
    # 단, 결제하기는 실수 결제 방지를 위해 정확히 가리켰을 때만 눌림.
    w, (WEL, MENU, DONE) = _make_window()
    app = _get_app()
    try:
        w.resize(1080, 1920)
        w.show()
        w._go_menu()
        w._add_to_cart(menu_data.get_item("burger_bulgogi"))
        for _ in range(5):
            app.processEvents()
        central = w.centralWidget()

        def aim_near(widget, off_x, off_y):
            c = widget.mapTo(central, widget.rect().center())
            w._cursor_nx = (c.x() + off_x) / central.width()
            w._cursor_ny = (c.y() + off_y) / central.height()
            w.cursor.show()

        plus = next(b for b in w.cart_host.findChildren(type(w.voice_btn))
                    if b.isVisible() and b.text().strip() in ("+", "＋"))
        aim_near(plus, 0, plus.height() // 2 + 25)        # 버튼 아래로 25px 빗나감
        assert w._button_at(central, int(w._cursor_nx * central.width()),
                            int(w._cursor_ny * central.height())) is not plus
        before = w.cart.item_count()
        w._handle_gesture_action("pinch")
        assert w.cart.item_count() == before + 1          # 가까운 + 가 눌림
        aim_near(w.checkout_btn, 0, -(w.checkout_btn.height() // 2 + 20))   # 결제하기 위로 20px
        w._handle_gesture_action("pinch")
        assert w.stack.currentIndex() == MENU              # 결제로 넘어가지 않음
    finally:
        w.close()


def test_gui_dwell_does_not_repeat():
    # 드웰(2초 머물기)로 메뉴를 담은 뒤 커서가 그 메뉴 위에 계속 있어도 또 담기지 않아야 함.
    # 커서가 벗어났다가 돌아오면 다시 담을 수 있음.
    w, (WEL, MENU, DONE) = _make_window()
    app = _get_app()
    try:
        w.resize(1080, 1920)
        w.show()
        w._go_menu()
        for _ in range(5):
            app.processEvents()
        central = w.centralWidget()
        card = w.menu_grid.itemAt(0).widget()
        c = card.mapTo(central, card.rect().center())
        nx, ny = c.x() / central.width(), c.y() / central.height()
        w._cursor_nx, w._cursor_ny = nx, ny
        w.cursor.show()

        def dwell_cycle(x, y):
            w._update_dwell(x, y)                              # 머무름 시작
            w._dwell_start_ms -= config.DWELL_SELECT_MS + 10   # 2초 경과
            w._last_gesture_action_ms = 0.0
            w._update_dwell(x, y)

        dwell_cycle(nx, ny)
        assert w.cart.item_count() == 1
        for _ in range(3):                                     # 그대로 머물러도 추가로 안 담김
            dwell_cycle(nx, ny)
        assert w.cart.item_count() == 1
        w._cursor_nx, w._cursor_ny = 0.02, 0.02                # 메뉴 밖으로 나감
        w._update_dwell(0.02, 0.02)
        w._cursor_nx, w._cursor_ny = nx, ny                    # 다시 돌아와 머무름
        dwell_cycle(nx, ny)
        assert w.cart.item_count() == 2
    finally:
        w.close()


def test_gui_menu_layout_same_in_all_modes():
    # 화면 모드가 바뀌어도 메뉴 순서와 위치(줄·칸)가 같아야 함
    w, (WEL, MENU, DONE) = _make_window()
    try:
        w._go_menu()
        layouts = []
        for mode in (config.MODE_STANDARD, config.MODE_SILVER,
                     config.MODE_CHILD, config.MODE_HIGH_CONTRAST):
            w._set_mode(mode)
            cells = []
            for i in range(w.menu_grid.count()):
                r, col, _, _ = w.menu_grid.getItemPosition(i)
                cells.append((w.menu_grid.itemAt(i).widget().item.item_id, r, col))
            layouts.append(sorted(cells))
        assert all(lay == layouts[0] for lay in layouts), layouts
    finally:
        w.close()


def test_gui_voice_text_defers_checkout():
    # 음성 주문 창에서 '…주시고 결제할게요'라고 하면 담고, 결제는 창을 닫은 뒤에 하도록 알려 줌
    w, (WEL, MENU, DONE) = _make_window()
    try:
        w.tr.set_lang("ko")
        w._go_menu()
        res = w._voice_text("불고기버거 하나 주시고 결제할게요")
        assert res["checkout"] is True and res["added"] == 1
        assert w.stack.currentIndex() == MENU                  # 아직 결제 화면으로 안 넘어감
        res2 = w._voice_text("결제할게요")                     # 이미 담긴 상태에서 결제만
        assert res2["checkout"] is True
        w._clear_cart()
        res3 = w._voice_text("결제할게요")                     # 빈 장바구니 결제 요청은 거절
        assert res3["checkout"] is False
    finally:
        w.close()


def test_voice_dialog_conversation():
    # 대화식 음성 창: 알아들은 말은 확인 없이 바로 담고, '결제'면 창을 닫고 결제 요청
    from ui.voice_dialog import VoiceOrderDialog
    _get_app()
    calls = []

    def on_text(t):
        calls.append(t)
        return {"added": 1, "checkout": "결제" in t, "understood": True,
                "message": "담았어요", "lang": "ko"}

    d = VoiceOrderDialog("ko", "힌트", "듣는 중", None, speaker=None, auto_listen=False,
                         on_text=on_text, can_checkout=lambda: True)
    d.show()
    d._on_recognized("콜라 하나 주세요")
    assert calls == ["콜라 하나 주세요"] and d.isVisible()
    assert d.input.text() == "" and not d.checkout_requested
    d._on_recognized("결제할게요")
    assert d.checkout_requested and not d.isVisible()


def test_voice_multilang_picks_english():
    # 세 언어로 동시에 인식해 가장 믿을 만한 결과를 고름(화면이 한국어여도 영어·중국어 말을 알아들음)
    from ui import voice_dialog as vd
    assert vd.looks_english_in_hangul("투 치즈버거스 앤 어 라지 콕 플리즈")
    assert not vd.looks_english_in_hangul("불고기버거 세트 하나 주세요")

    class _Sr:
        class UnknownValueError(Exception):
            pass

        class RequestError(Exception):
            pass

    def fake(answers):
        class _Rec:
            def recognize_google(self, audio, language=None, show_all=False):
                text, conf = answers[language]
                return {"alternative": [{"transcript": text, "confidence": conf}], "final": True}
        return _Rec()

    def pick(ui_lang, answers):
        got = []
        worker = vd.SpeechWorker(ui_lang)
        worker.recognized.connect(got.append)
        worker._recognize_order(_Sr, fake(answers), object())
        return got[0] if got else None

    # 화면 한국어 + 영어로 말함
    assert pick("ko", {"ko-KR": ("투 치즈버거스 앤 어 라지 콕 플리즈", 0.62),
                       "en-US": ("two cheeseburgers and a large coke please", 0.91),
                       "zh-CN": ("两个", 0.30)}) == "two cheeseburgers and a large coke please"
    # 화면 한국어 + 중국어로 말함
    assert pick("ko", {"ko-KR": ("량거 쑤앙청", 0.41),
                       "en-US": ("liang ge", 0.35),
                       "zh-CN": ("两个双层芝士汉堡", 0.88)}) == "两个双层芝士汉堡"
    # 영어로 말했는데 중국어 인식기가 엉터리 'QQQ'를 높은 신뢰도로 돌려줘도 영어를 고름
    assert pick("ko", {"ko-KR": ("", 0.0),
                       "en-US": ("hello there", 0.80),
                       "zh-CN": ("QQQ", 0.95)}) == "hello there"
    # 화면 한국어 + 한국어로 말함
    assert pick("ko", {"ko-KR": ("불고기버거 세트 하나 주세요", 0.93),
                       "en-US": ("bull go", 0.40),
                       "zh-CN": ("不过", 0.30)}) == "불고기버거 세트 하나 주세요"


def test_nlu_gyeoljae_means_checkout():
    # 음성 인식이 '결제'를 '결재'로 받아 적어도 결제로 알아들어야 함
    from core.nlu import parse_order
    for t in ("결재 해줘", "이제 결재할게요", "결제 해줘", "That's all", "check out please"):
        assert any(i.action == "checkout" for i in parse_order(t).intents), t


def test_gui_cart_scrollbar_hidden_but_scrolls():
    # 장바구니 스크롤바는 숨기되, 손동작 스와이프로는 넘어가야 함
    from PyQt6.QtCore import Qt
    w, (WEL, MENU, DONE) = _make_window()
    app = _get_app()
    try:
        w.resize(1080, 1920)
        w.show()
        w._go_menu()
        for item in menu_data.MENU[:8]:
            w._add_to_cart(item)
        for _ in range(5):
            app.processEvents()
        assert w.cart_scroll.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        bar = w.cart_scroll.verticalScrollBar()
        assert bar.maximum() > 0
        central = w.centralWidget()
        c = w.cart_scroll.mapTo(central, w.cart_scroll.rect().center())
        w._cursor_nx, w._cursor_ny = c.x() / central.width(), c.y() / central.height()
        w.cursor.show()
        w._handle_gesture_action("swipe_up")
        w._scroll_anim.setCurrentTime(w._scroll_anim.duration())
        assert bar.value() > 0
    finally:
        w.close()


def test_aim_map_elastic():
    # 탄력 조준: 손을 카메라 아래쪽에서 처음 들어도 화면 맨 위·맨 아래에 모두 닿아야 하고,
    # 손이 한참 안 보였다가 다시 들면 그곳을 기준으로 다시 맞춤
    vt = vision_mod.VisionThread()
    clock = [1000.0]
    orig = vision_mod.time.time
    vision_mod.time.time = lambda: clock[0]
    try:
        sx, sy = vt._aim_map("open_palm", 0.5, 0.85)          # 카메라 아래쪽에서 처음 듦
        assert abs(sx - 0.5) < 1e-9 and 0.5 < sy < 1.0
        assert vt._aim_map("open_palm", 0.5, 0.95)[1] > 0.99   # 카메라 아래 끝 → 화면 맨 아래
        assert vt._aim_map("open_palm", 0.5, 0.30)[1] < 0.01   # 손을 들면 화면 맨 위(범위가 따라옴)
        assert vt._aim_map("open_palm", 0.5, 0.95)[1] > 0.99   # 다시 내리면 다시 맨 아래
        assert vt._aim_map("open_palm", 0.97, 0.6)[0] > 0.99   # 오른쪽 끝
        clock[0] += config.AIM_RECENTER_AFTER_S + 1             # 손이 한참 안 보였다가
        sx, sy = vt._aim_map("open_palm", 0.5, 0.5)             # 다시 들면 그곳이 가운데
        assert abs(sx - 0.5) < 1e-9 and abs(sy - 0.5) < 1e-9
    finally:
        vision_mod.time.time = orig


def test_gui_swipe_up_scrolls_menu():
    # 손바닥 위로 휘두르기 → 메뉴 목록이 아래쪽으로 넘어감, 아래로 → 다시 위로
    w, (WEL, MENU, DONE) = _make_window()
    app = _get_app()
    try:
        w.resize(1080, 1200)
        w.show()
        w._go_menu()
        w._manual_set_mode(config.MODE_SILVER)            # 큰 카드 → 스크롤이 생김
        for _ in range(5):
            app.processEvents()
        bar = w.menu_scroll.verticalScrollBar()
        assert bar.maximum() > 0
        w.cursor.hide()
        w._handle_gesture_action("swipe_up")
        w._scroll_anim.setCurrentTime(w._scroll_anim.duration())   # 애니메이션 끝으로
        assert bar.value() > 0
        w._handle_gesture_action("swipe_down")
        w._scroll_anim.setCurrentTime(w._scroll_anim.duration())
        assert bar.value() == 0
    finally:
        w.close()


def test_gui_contrast_button_sync():
    # 헤더 고대비 버튼: 켜면 고대비, 끄면 직전 화면. 다른 경로로 바뀌어도 버튼 상태가 맞아야 함
    w, (WEL, MENU, DONE) = _make_window()
    try:
        w._manual_set_mode(config.MODE_SILVER)
        assert not w.contrast_btn.isChecked()
        w.contrast_btn.click()                                # 켜기
        assert w.mode == config.MODE_HIGH_CONTRAST and w.contrast_btn.isChecked()
        assert w._auto_mode_locked
        w.contrast_btn.click()                                # 끄기 → 직전 화면(실버)
        assert w.mode == config.MODE_SILVER and not w.contrast_btn.isChecked()
        w._manual_set_mode(config.MODE_HIGH_CONTRAST)         # 시연 도구로 켜도 버튼 동기화
        assert w.contrast_btn.isChecked()
        w._manual_set_mode(config.MODE_CHILD)
        assert not w.contrast_btn.isChecked()
    finally:
        w.close()


def test_gui_voice_result_is_spoken():
    # 음성 주문 결과(담은 메뉴·합계), 비우기, 못 알아들음을 모두 소리로 안내해야 함
    w, (WEL, MENU, DONE) = _make_window()
    said = []
    try:
        w.speaker.say = said.append
        w.tr.set_lang("ko")
        w._go_menu()
        w._process_order_text("불고기버거 세트 하나 주세요")
        total = f"{5500 + menu_data.SET_EXTRA_PRICE:,}"          # 8,200
        assert any("불고기버거 세트 1개" in s and total in s for s in said), said
        said.clear()
        w._process_order_text("전부 삭제해줘")
        assert said == [TEXTS["ko"]["cleared_tts"]]
        said.clear()
        w._process_order_text("오늘 날씨가 좋네요")
        assert said == [TEXTS["ko"]["not_understood"]]
    finally:
        w.close()


def test_gui_portrait_fits_standbyme():
    # LG 스탠바이미 세로 화면(1080×1920): 모든 모드 × 언어에서 창이 화면보다 커지지 않고,
    # 버튼·목록이 충분히 크며 접근성 버튼 글자가 잘리지 않아야 함(큰 글씨 모드 폭 넘침 회귀 방지)
    from ui.widgets import ChoiceDialog
    from ui.voice_dialog import VoiceOrderDialog
    w, (WEL, MENU, DONE) = _make_window()
    app = _get_app()

    def settle():
        for _ in range(3):
            app.processEvents()

    try:
        assert (config.WINDOW_WIDTH, config.WINDOW_HEIGHT) == (1080, 1920)
        w.resize(1080, 1920)
        w.show()
        for lang in ("ko", "en", "zh"):
            for mode in (config.MODE_STANDARD, config.MODE_SILVER,
                         config.MODE_CHILD, config.MODE_HIGH_CONTRAST):
                tag = f"{lang}/{mode}"
                w.tr.set_lang(lang)
                w.mode = mode
                w._apply_theme()
                settle()
                assert (w.width(), w.height()) == (1080, 1920), (tag, w.size())  # 첫 화면
                assert w.start_btn.width() >= 900 and w.start_btn.height() >= 140, tag
                assert w.welcome_voice_btn.height() >= 100, tag
                # 접근성 버튼 4개는 화면 폭을 똑같이 나눠 씀(글자 크기 고정 → 실제 글꼴 최대 약 200px)
                for b in (w.lang_btn, w.contrast_btn, w.tts_btn, w.gesture_btn):
                    assert b.width() >= 240 and b.height() >= 80, (tag, b.size())

                w._go_menu()
                w._add_to_cart(menu_data.get_item("burger_double_cheese"), is_set=True)
                w._add_to_cart(menu_data.get_item("drink_cola"))
                settle()
                assert (w.width(), w.height()) == (1080, 1920), (tag, w.size())  # 메뉴 화면
                assert w.menu_scroll.viewport().height() >= 450, tag
                assert w.cart_scroll.viewport().height() >= 140, tag
                assert w.checkout_btn.height() >= 90, tag

                w._checkout()
                settle()
                assert (w.width(), w.height()) == (1080, 1920), (tag, w.size())  # 완료 화면
                w._reset_session()

                # 접근성 안내창·음성 주문 창도 세로 화면 폭 안에 들어와야 함
                t = TEXTS[lang]
                box = ChoiceDialog(t["a11y_ask_title"], t["a11y_ask"], t["a11y_yes"],
                                   t["a11y_no"], style=w.styleSheet(), parent=w)
                assert box.width() <= 1080 and box.height() <= 1920, (tag, box.size())
                box.deleteLater()
                dlg = VoiceOrderDialog(lang, t["voice_hint"], t["listening"], w,
                                       theme=theme_mod.get_theme(mode))
                dlg.setStyleSheet(w.styleSheet())
                dlg.adjustSize()
                assert dlg.width() <= 1080 and dlg.height() <= 1920, (tag, dlg.size())
                dlg.deleteLater()
    finally:
        w.close()


# ══════════════════════════════════════════════
# 실행기
# ══════════════════════════════════════════════
def _run_all():
    tests = [(k, v) for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed, failed = 0, []
    for name, fn in tests:
        try:
            fn()
            print(f"  [PASS] {name}")
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {name}: {e}")
            failed.append(name)
        except Exception as e:
            import traceback
            print(f"  [ERR ] {name}: {type(e).__name__}: {e}")
            traceback.print_exc()
            failed.append(name)
    print(f"\n결과: {passed}/{len(tests)} 통과")
    if failed:
        print("실패:", ", ".join(failed))
    return not failed


if __name__ == "__main__":
    print("===== 유니버셜 키오스크 전체 시뮬레이션 검증 =====")
    ok = _run_all()
    sys.exit(0 if ok else 1)
