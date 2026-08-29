"""
tests/test_scenarios.py — 사용자 시나리오(User Case) 완전탐색 E2E 테스트
========================================================================
실제 손님이 키오스크 앞에서 할 수 있는 '모든 행동'을 시나리오(UC)별로
처음부터 끝까지(End-to-End) 재현하여 검증합니다. test_full.py 가 모듈 단위
검증이라면, 이 파일은 '사용자 여정' 단위 검증입니다.

시나리오 그룹
  UC-A  터치 주문            UC-F  익명 단골 인식
  UC-B  음성 주문(NLU)       UC-G  세션/상태 머신
  UC-C  손동작 제어          UC-H  판매 데이터
  UC-D  접근성 모드          UC-I  가격 정확성(회귀)
  UC-E  다국어               UC-J  강건성/예외

실행:
    python tests/test_scenarios.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # 화면 없이 GUI 테스트

import numpy as np

import config
config.VISION_ENABLED = False
config.TTS_ENABLED = False
import core.speech as _speech_mod
_speech_mod.TTS_ENABLED = False

# DB 오염 방지: 모든 KioskDatabase 를 인메모리로 강제(테스트 격리)
import core.database as _db_mod
_db_mod.KioskDatabase.__init__.__defaults__ = (":memory:",)

from core import menu_data, vision as vision_mod
from core.order import Cart
from core.database import KioskDatabase
from core.regulars import RegularManager
from core.i18n import TEXTS


# ══════════════════════════════════════════════
# 합성 손 랜드마크(현실적 기하) — 손동작 시나리오용
# ══════════════════════════════════════════════
class _LM:
    __slots__ = ("x", "y", "z")
    def __init__(self, x=0.5, y=0.5, z=0.0):
        self.x, self.y, self.z = x, y, z


class _Hand:
    def __init__(self, lms):
        self.landmark = lms


def make_hand(thumb, index, middle, ring, pinky, palm=(0.5, 0.5), fold_y=-0.18):
    """현실적인 손 랜드마크 생성. fold_y 로 접힘 깊이를 조절(강건성 테스트용)."""
    px, py = palm
    lms = [_LM(px, py) for _ in range(21)]

    def put(i, dx, dy):
        lms[i].x, lms[i].y = px + dx, py + dy

    put(0, 0.0, 0.0)
    put(1, -0.06, -0.04); put(2, -0.10, -0.09); put(3, -0.15, -0.14)
    put(4, -0.24, -0.20) if thumb else put(4, -0.05, -0.10)
    for on, mcp, pip, dip, tip, ox in [
            (index, 5, 6, 7, 8, -0.05),
            (middle, 9, 10, 11, 12, 0.0),
            (ring, 13, 14, 15, 16, 0.05),
            (pinky, 17, 18, 19, 20, 0.09)]:
        put(mcp, ox, -0.26)
        put(pip, ox, -0.40)
        put(dip, ox, -0.48)
        put(tip, ox, -0.60 if on else fold_y)
    return _Hand(lms)


# ══════════════════════════════════════════════
# GUI 윈도우 도우미
# ══════════════════════════════════════════════
_APP = None
def _app():
    global _APP
    from PyQt6.QtWidgets import QApplication
    _APP = QApplication.instance() or QApplication(sys.argv)
    return _APP


def _win():
    _app()
    from ui.main_window import (KioskMainWindow, SCREEN_WELCOME,
                                SCREEN_MENU, SCREEN_DONE)
    w = KioskMainWindow()
    return w, (SCREEN_WELCOME, SCREEN_MENU, SCREEN_DONE)


def _shown_menu_window():
    """실제 위젯 크기를 갖도록 띄운 뒤 메뉴 화면으로 보낸 윈도우."""
    w, screens = _win()
    w.resize(1280, 800)
    w.show()
    _app().processEvents()
    w._go_menu()
    _app().processEvents()
    return w, screens


def _norm_center(w, card):
    """카드 중심의 정규화 좌표(0~1)를 구한다."""
    central = w.centralWidget()
    c = card.mapTo(central, card.rect().center())
    return c.x() / max(1, central.width()), c.y() / max(1, central.height())


# ══════════════════════════════════════════════
# UC-A  터치 주문
# ══════════════════════════════════════════════
def test_UC_A1_touch_single_order_to_checkout():
    w, (WEL, MENU, DONE) = _win()
    try:
        w._go_menu()
        w._add_to_cart(menu_data.get_item("burger_bulgogi"))
        assert w.cart.item_count() == 1
        w._checkout()
        assert w.stack.currentIndex() == DONE
    finally:
        w.close()


def test_UC_A2_touch_qty_change_and_remove():
    w, (WEL, MENU, DONE) = _win()
    try:
        w._go_menu()
        w._add_to_cart(menu_data.get_item("burger_bulgogi"))
        w._on_cart_qty(0, +2)
        assert w.cart.lines[0].qty == 3
        w._on_cart_qty(0, -1)
        assert w.cart.lines[0].qty == 2
        w._on_cart_remove(0)
        assert w.cart.is_empty()
    finally:
        w.close()


def test_UC_A3_touch_set_price():
    w, (WEL, MENU, DONE) = _win()
    try:
        w._go_menu()
        w.set_toggle.setChecked(True)
        w._toggle_set()
        w._add_to_cart(menu_data.get_item("burger_bulgogi"))   # 세트로 담김
        line = w.cart.lines[0]
        assert line.is_set
        assert line.unit_price() == 5500 + menu_data.SET_EXTRA_PRICE   # 8200
    finally:
        w.close()


def test_UC_A4_touch_clear_all():
    w, (WEL, MENU, DONE) = _win()
    try:
        w._go_menu()
        w._add_to_cart(menu_data.get_item("burger_bulgogi"))
        w._add_to_cart(menu_data.get_item("drink_cola"))
        w._clear_cart()
        assert w.cart.is_empty()
    finally:
        w.close()


def test_UC_A5_empty_checkout_blocked():
    w, (WEL, MENU, DONE) = _win()
    try:
        w._go_menu()
        w._checkout()
        assert w.stack.currentIndex() != DONE      # 빈 장바구니 → 완료화면 금지
        assert w._busy is False                    # busy 플래그도 세워지지 않음
    finally:
        w.close()


# ══════════════════════════════════════════════
# UC-B  음성 주문(NLU)
# ══════════════════════════════════════════════
def test_UC_B1_voice_korean_single():
    w, (WEL, MENU, DONE) = _win()
    try:
        w.tr.set_lang("ko"); w._go_menu()
        w._process_order_text("불고기버거 하나 주세요")
        assert w.cart.item_count() == 1
    finally:
        w.close()


def test_UC_B2_voice_korean_multi_and_set():
    w, (WEL, MENU, DONE) = _win()
    try:
        w.tr.set_lang("ko"); w._go_menu()
        w._process_order_text("새우버거 세트 두개 주세요")
        line = [l for l in w.cart.lines if l.item.item_id == "burger_shrimp"][0]
        assert line.is_set and line.qty == 2
    finally:
        w.close()


def test_UC_B3_voice_qty_no_contamination():
    w, (WEL, MENU, DONE) = _win()
    try:
        w.tr.set_lang("ko"); w._go_menu()
        w._process_order_text("더블 치즈버거 두개랑 콜라 주세요")
        by = {l.item.item_id: l for l in w.cart.lines}
        assert by["burger_double_cheese"].qty == 2
        assert by["drink_cola"].qty == 1           # 수량 오염 없음
    finally:
        w.close()


def test_UC_B4_voice_english_auto_switch():
    w, (WEL, MENU, DONE) = _win()
    try:
        w.tr.set_lang("ko"); w._go_menu()
        w._process_order_text("I want a shrimp burger set")
        assert w.tr.lang == "en"
        assert any(l.item.item_id == "burger_shrimp" for l in w.cart.lines)
    finally:
        w.close()


def test_UC_B5_voice_clear_command():
    w, (WEL, MENU, DONE) = _win()
    try:
        w.tr.set_lang("ko"); w._go_menu()
        w._add_to_cart(menu_data.get_item("burger_bulgogi"))
        w._process_order_text("전부 비워주세요")
        assert w.cart.is_empty()
    finally:
        w.close()


def test_UC_B6_voice_unrecognized_is_safe():
    w, (WEL, MENU, DONE) = _win()
    try:
        w.tr.set_lang("ko"); w._go_menu()
        before = w.cart.item_count()
        w._process_order_text("오늘 날씨가 좋네요")     # 메뉴 아님
        assert w.cart.item_count() == before          # 아무것도 담기지 않음(안전)
    finally:
        w.close()


def test_UC_B7_voice_hanwoo_not_one():
    w, (WEL, MENU, DONE) = _win()
    try:
        w.tr.set_lang("ko"); w._go_menu()
        w._process_order_text("한우불고기버거 주세요")
        line = [l for l in w.cart.lines if l.item.item_id == "burger_hanwoo"]
        assert line and line[0].qty == 1              # '한'우 → 수량 1로 오인 안 함
    finally:
        w.close()


# ══════════════════════════════════════════════
# UC-C  손동작 제어
# ══════════════════════════════════════════════
def test_UC_C1_recognizer_point_moves_cursor():
    gr = vision_mod.GestureRecognizer()
    name, (x, y) = gr.classify(make_hand(False, True, False, False, False))
    assert name == "point"


def test_UC_C2_point_then_fist_adds_pointed_item():
    from ui.widgets import MenuCard
    w, (WEL, MENU, DONE) = _shown_menu_window()
    try:
        card = w.menu_grid.itemAt(0).widget()
        assert isinstance(card, MenuCard)
        nx, ny = _norm_center(w, card)
        w._gesture_enabled = True
        w._busy = False
        w._last_gesture_action_ms = 0.0
        w._on_gesture("point", nx, ny)             # 메뉴를 가리킴(커서 이동)
        w._on_gesture("fist", 0.99, 0.99)          # 주먹: 좌표 무시, 가리킨 위치 사용
        ids = [l.item.item_id for l in w.cart.lines]
        assert card.item.item_id in ids            # 가리킨 그 메뉴가 담김
    finally:
        w.close()


def test_UC_C3_swipe_changes_category():
    w, (WEL, MENU, DONE) = _win()
    try:
        w._go_menu()
        start = w.current_category
        w._gesture_enabled = True; w._busy = False; w._last_gesture_action_ms = 0.0
        w._on_gesture("swipe_right", 0.5, 0.5)
        assert w.current_category != start
    finally:
        w.close()


def test_UC_C4_gesture_toggle_off_ignored():
    w, (WEL, MENU, DONE) = _win()
    try:
        w._go_menu()
        start = w.current_category
        w.gesture_btn.setChecked(False); w._toggle_gesture()
        w._on_gesture("swipe_right", 0.5, 0.5)
        assert w.current_category == start         # 꺼짐 → 무시
    finally:
        w.close()


def test_UC_C5_gesture_cooldown_blocks_repeat():
    w, (WEL, MENU, DONE) = _win()
    try:
        w._go_menu()
        w._select_category(menu_data.CATEGORY_ORDER[0])
        w._gesture_enabled = True; w._busy = False; w._last_gesture_action_ms = 0.0
        w._on_gesture("swipe_right", 0.5, 0.5)
        after = w.current_category
        w._on_gesture("swipe_right", 0.5, 0.5)     # 쿨다운 내 → 무시
        assert w.current_category == after
    finally:
        w.close()


def test_UC_C6_gesture_ignored_when_busy():
    w, (WEL, MENU, DONE) = _win()
    try:
        w._go_menu()
        before = w.current_category
        w._gesture_enabled = True; w._busy = True; w._last_gesture_action_ms = 0.0
        w._on_gesture("swipe_right", 0.5, 0.5)
        assert w.current_category == before        # 처리 중 → 무시
    finally:
        w.close()


def test_UC_C7_closed_hand_is_robust_fist():
    # 손가락이 약간 노이즈로 들려도 닫힌 손은 'fist' 로 인식돼야 함(idle 금지)
    for fold in (-0.18, -0.28, -0.34):             # 접힘 깊이를 점점 얕게(노이즈)
        gr = vision_mod.GestureRecognizer()
        name = None
        for _ in range(config.FIST_HOLD_FRAMES):
            name, _pos = gr.classify(make_hand(False, False, False, False, False,
                                               fold_y=fold))
        assert name == "fist", f"fold={fold} → {name}"


def test_UC_C8_fist_does_not_jump_cursor():
    # point 로 가리킨 위치를 fist 가 그대로 사용(엉뚱한 좌표로 점프 금지)
    from ui.widgets import MenuCard
    w, (WEL, MENU, DONE) = _shown_menu_window()
    try:
        card = w.menu_grid.itemAt(1).widget()      # 두 번째 카드
        nx, ny = _norm_center(w, card)
        w._gesture_enabled = True; w._busy = False; w._last_gesture_action_ms = 0.0
        w._on_gesture("point", nx, ny)
        saved = (w._cursor_nx, w._cursor_ny)
        w._on_gesture("fist_hold", 0.1, 0.1)       # 쥐는 중: 커서 유지
        assert (w._cursor_nx, w._cursor_ny) == saved
        w._on_gesture("fist", 0.1, 0.1)            # 쥐기 완료
        assert any(l.item.item_id == card.item.item_id for l in w.cart.lines)
    finally:
        w.close()


def test_UC_C9_signyes_needs_hold_not_flicker():
    # 엄지가 한두 프레임 깜빡인다고 'sign_yes(결제)'가 발동하면 안 됨(우발 결제 방지)
    gr = vision_mod.GestureRecognizer()
    flicker = gr.classify(make_hand(True, False, False, False, False))[0]
    assert flicker != "sign_yes"                   # 첫 프레임에는 확정 금지
    # 충분히(FIST_HOLD_FRAMES 만큼) 유지하면 그제서야 sign_yes 확정
    name = flicker
    for _ in range(config.FIST_HOLD_FRAMES - 1):
        name = gr.classify(make_hand(True, False, False, False, False))[0]
    assert name == "sign_yes"


def test_UC_C10_thumb_out_fist_does_not_checkout():
    # 주먹을 쥐며 엄지가 살짝 나온 정도로는 결제 화면으로 넘어가지 않아야 함
    w, (WEL, MENU, DONE) = _win()
    try:
        w._go_menu()
        w._add_to_cart(menu_data.get_item("burger_bulgogi"))
        w._gesture_enabled = True; w._busy = False; w._last_gesture_action_ms = 0.0
        w._on_gesture("sign_hold", 0.5, 0.5)       # 유지 중(미확정) → 무시
        assert w.stack.currentIndex() == MENU      # 결제 화면으로 넘어가지 않음
    finally:
        w.close()


# ══════════════════════════════════════════════
# UC-D  접근성 모드(연령/고대비)
# ══════════════════════════════════════════════
def test_UC_D1_to_D4_all_modes_apply():
    w, (WEL, MENU, DONE) = _win()
    try:
        for mode in (config.MODE_CHILD, config.MODE_SILVER,
                     config.MODE_HIGH_CONTRAST, config.MODE_STANDARD):
            w._manual_set_mode(mode)
            assert w.mode == mode
    finally:
        w.close()


def test_UC_D5_age_majority_vote_switch():
    w, (WEL, MENU, DONE) = _win()
    try:
        w._auto_mode_locked = False
        w._last_auto_switch_ms = 0.0
        w.mode = config.MODE_STANDARD
        for _ in range(config.AGE_VOTE_WINDOW):    # 충분한 'senior' 표
            w._on_age_group("senior")
        assert w.mode == config.MODE_SILVER        # 다수결 → 실버 모드
    finally:
        w.close()


def test_UC_D6_age_switch_respects_lock():
    w, (WEL, MENU, DONE) = _win()
    try:
        w._manual_set_mode(config.MODE_CHILD)      # 수동 고정
        w._auto_mode_locked = True
        for _ in range(config.AGE_VOTE_WINDOW):
            w._on_age_group("senior")
        assert w.mode == config.MODE_CHILD         # 잠금 → 자동전환 안 함
    finally:
        w.close()


# ══════════════════════════════════════════════
# UC-E  다국어
# ══════════════════════════════════════════════
def test_UC_E1_language_toggle():
    w, (WEL, MENU, DONE) = _win()
    try:
        w.tr.set_lang("ko")
        w._toggle_language()
        assert w.tr.lang == "en"
        w._toggle_language()
        assert w.tr.lang == "zh"
        w._toggle_language()
        assert w.tr.lang == "ko"
    finally:
        w.close()


def test_UC_E2_text_key_parity():
    ko, en, zh = set(TEXTS["ko"]), set(TEXTS["en"]), set(TEXTS["zh"])
    assert ko == en == zh                          # 모든 문구 키가 세 언어에 존재


# ══════════════════════════════════════════════
# UC-F  익명 단골 인식
# ══════════════════════════════════════════════
def test_UC_F1_register_recognize_welcome():
    db = KioskDatabase()
    mgr = RegularManager(db)
    rng = np.random.default_rng(3)
    emb = rng.random(72)
    fav = Cart(); fav.add(menu_data.get_item("burger_bulgogi"))
    mgr.register("단골1", emb, fav.snapshot_favorite())
    mgr.reset_tracking()
    result = None
    for _ in range(config.FACE_MATCH_STABLE_FRAMES):
        result = mgr.recognize(emb)                # 같은 얼굴 연속 → 확정
    assert result is not None and result["nickname"] == "단골1"
    db.close()


def test_UC_F1b_recognize_announces_only_once():
    # 같은 단골이 카메라에 계속 잡혀도 환영은 '한 번'만(대화상자 중복 스태킹 방지)
    db = KioskDatabase()
    mgr = RegularManager(db)
    emb = np.random.default_rng(11).random(72)
    fav = Cart(); fav.add(menu_data.get_item("burger_bulgogi"))
    mgr.register("단골X", emb, fav.snapshot_favorite())
    mgr.reset_tracking()
    hits = sum(mgr.recognize(emb) is not None
               for _ in range(config.FACE_MATCH_STABLE_FRAMES + 30))
    assert hits == 1                               # 60프레임 들어와도 단 1회만 확정
    mgr.reset_tracking()                           # 손님이 떠났다 다시 오면
    again = None
    for _ in range(config.FACE_MATCH_STABLE_FRAMES):
        again = mgr.recognize(emb)
    assert again is not None                       # 다시 인식 가능
    db.close()



def test_UC_F2_use_favorite_one_click():
    w, (WEL, MENU, DONE) = _win()
    try:
        fav = Cart()
        fav.add(menu_data.get_item("burger_double_cheese"), is_set=True, drink_size="L")
        emb = np.random.default_rng(7).random(72)
        w.last_embedding = emb
        rid = w.regulars.register("VIP1", emb, fav.snapshot_favorite())
        reg = next(r for r in w.regulars._regulars if r["id"] == rid)
        # 환영 대화상자 없이 즐겨찾기 복원 로직만 직접 검증
        restored = Cart.from_favorite(reg["favorite"])
        assert restored.item_count() == fav.item_count()
        assert restored.total() == fav.total()
    finally:
        w.close()


def test_UC_F3_registration_offer_no_duplicate():
    # 결제 재진입(중첩 루프 모사)에도 등록 제안이 한 번만 열려야 함
    w, (WEL, MENU, DONE) = _win()
    try:
        w._go_menu()
        w._add_to_cart(menu_data.get_item("burger_bulgogi"))
        w.last_embedding = np.random.default_rng(1).random(72)
        w.active_regular = None
        calls = {"n": 0}
        def fake_offer():
            calls["n"] += 1
            w._checkout()                          # 재진입 시도
        w._offer_regular_registration = fake_offer
        w._checkout()
        assert calls["n"] == 1
    finally:
        w.close()


def test_UC_F4_unique_nickname():
    db = KioskDatabase()
    mgr = RegularManager(db)
    n1 = mgr.suggest_nickname("단골")
    mgr.register(n1, np.random.default_rng(2).random(72),
                 Cart().snapshot_favorite())
    n2 = mgr.suggest_nickname("단골")
    assert n1 != n2                                # 중복되지 않는 새 별명
    db.close()


# ══════════════════════════════════════════════
# UC-G  세션/상태 머신
# ══════════════════════════════════════════════
def test_UC_G1_session_reset_clears_state():
    w, (WEL, MENU, DONE) = _win()
    try:
        w._go_menu()
        w._add_to_cart(menu_data.get_item("burger_bulgogi"))
        w.set_mode_on = True
        w._busy = True
        w._reset_session()
        assert w.cart.is_empty()
        assert w.set_mode_on is False
        assert w._busy is False
        assert w.stack.currentIndex() == WEL
    finally:
        w.close()


def test_UC_G2_welcome_to_done_flow():
    w, (WEL, MENU, DONE) = _win()
    try:
        assert w.stack.currentIndex() == WEL
        w._go_menu()
        assert w.stack.currentIndex() == MENU
        w._add_to_cart(menu_data.get_item("burger_bulgogi"))
        w._checkout()
        assert w.stack.currentIndex() == DONE
    finally:
        w.close()


# ══════════════════════════════════════════════
# UC-H  판매 데이터
# ══════════════════════════════════════════════
def test_UC_H1_order_recorded_in_db():
    w, (WEL, MENU, DONE) = _win()
    try:
        w._go_menu()
        w._add_to_cart(menu_data.get_item("burger_bulgogi"))
        total_before = w.db.sales_summary().get("total_revenue", 0)
        w._checkout()
        summary = w.db.sales_summary()
        assert summary["order_count"] >= 1
        assert summary["total_revenue"] >= total_before + 5500
    finally:
        w.close()


# ══════════════════════════════════════════════
# UC-I  가격 정확성(회귀)
# ══════════════════════════════════════════════
def test_UC_I1_plain_burger_no_size_surcharge():
    cart = Cart()
    cart.add(menu_data.get_item("burger_bulgogi"), drink_size="L")   # 단품
    assert cart.lines[0].unit_price() == 5500       # 추가요금 없음
    assert cart.total() == 5500


def test_UC_I2_set_option_change_single_line():
    w, (WEL, MENU, DONE) = _win()
    try:
        w.tr.set_lang("ko"); w._go_menu()
        w._process_order_text("불고기버거 세트 하나 주시는데 음료는 콜라 라지로 "
                              "바꾸고 사이드는 치즈스틱으로 바꿀게요")
        assert len(w.cart.lines) == 1               # 한 줄(이중청구 금지)
        expected = 5500 + menu_data.SET_EXTRA_PRICE + menu_data.SIZE_EXTRA_PRICE["L"]
        assert w.cart.total() == expected           # 8700
    finally:
        w.close()


# ══════════════════════════════════════════════
# UC-J  강건성/예외
# ══════════════════════════════════════════════
def test_UC_J1_empty_voice_text_safe():
    w, (WEL, MENU, DONE) = _win()
    try:
        w._go_menu()
        w._process_order_text("")                   # 빈 입력
        w._process_order_text("   ")                # 공백
        assert w.cart.is_empty()                    # 죽지 않고 안전
    finally:
        w.close()


def test_UC_J2_remove_invalid_index_safe():
    w, (WEL, MENU, DONE) = _win()
    try:
        w._go_menu()
        w._add_to_cart(menu_data.get_item("burger_bulgogi"))
        w.cart.remove_index(99)                     # 범위 밖 인덱스
        w.cart.change_qty(99, -1)
        assert w.cart.item_count() == 1             # 영향 없음(안전)
    finally:
        w.close()


def test_UC_J3_unknown_gesture_ignored():
    w, (WEL, MENU, DONE) = _win()
    try:
        w._go_menu()
        before = w.current_category
        w._gesture_enabled = True; w._busy = False; w._last_gesture_action_ms = 0.0
        w._on_gesture("zigzag", 0.5, 0.5)           # 정의되지 않은 제스처
        w._on_gesture("idle", 0.5, 0.5)
        assert w.current_category == before          # 아무 동작 안 함
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
    print("===== 유니버셜 키오스크 사용자 시나리오(E2E) 검증 =====")
    ok = _run_all()
    sys.exit(0 if ok else 1)
