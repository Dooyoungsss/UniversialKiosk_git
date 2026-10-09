"""
tests/test_kiosk.py — 핵심 기능 자동 검증
================================================
대회 심사위원이 한 줄로 "이 프로그램이 진짜 작동하는지" 확인할 수 있는 테스트입니다.

실행:
    python -m pytest tests/ -v          (pytest 가 있을 때)
    python tests/test_kiosk.py          (그냥 실행해도 됨)
"""
from __future__ import annotations

import os
import sys

# 상위 폴더를 import 경로에 추가(어디서 실행해도 동작하도록)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from core import menu_data
from core.mathutils import (euclidean_distance, cosine_similarity,
                            MovingAverageFilter, normalize_vector)
from core.order import Cart
from core.nlu import parse_order


# ──────────────────────────────────────────────
# 1) 수학 공식 (계획서 4.1)
# ──────────────────────────────────────────────
def test_euclidean_distance():
    # 3-4-5 직각삼각형: 거리는 5
    assert abs(euclidean_distance([0, 0], [3, 4]) - 5.0) < 1e-9


def test_cosine_similarity():
    assert abs(cosine_similarity([1, 2, 3], [1, 2, 3]) - 1.0) < 1e-9   # 같은 방향
    assert abs(cosine_similarity([1, 0], [0, 1]) - 0.0) < 1e-9          # 직각
    assert abs(cosine_similarity([1, 0], [-1, 0]) + 1.0) < 1e-9         # 반대


def test_moving_average_filter():
    maf = MovingAverageFilter(window=3)
    assert maf.update(0, 0) == (0.0, 0.0)
    assert maf.update(10, 10) == (5.0, 5.0)
    assert maf.update(20, 20) == (10.0, 10.0)   # (0+10+20)/3


# ──────────────────────────────────────────────
# 2) 메뉴 / 장바구니 (계획서 4.3 OOP)
# ──────────────────────────────────────────────
def test_menu_loaded():
    assert len(menu_data.MENU) >= 10
    assert len(menu_data.best_sellers()) >= 4          # 실버모드 4종 노출


def test_cart_total_with_set_and_size():
    cart = Cart()
    bulgogi = menu_data.get_item("burger_bulgogi")       # 5500
    cart.add(bulgogi, qty=1, is_set=True, drink_size="L")
    # 세트(+2700) + 라지(+500) = 8700
    expected = 5500 + menu_data.SET_EXTRA_PRICE + menu_data.SIZE_EXTRA_PRICE["L"]
    assert cart.total() == expected
    assert cart.item_count() == 1


def test_cart_merge_same_item():
    cart = Cart()
    fries = menu_data.get_item("side_fries")
    cart.add(fries, qty=1)
    cart.add(fries, qty=2)
    assert len(cart.lines) == 1            # 같은 메뉴는 합쳐짐
    assert cart.lines[0].qty == 3


# ──────────────────────────────────────────────
# 3) 자연어 주문 NLU (계획서 2.4)
# ──────────────────────────────────────────────
def test_nlu_complex_korean():
    r = parse_order("불고기버거 세트 하나 주시는데 음료는 콜라 라지로 바꾸고 "
                    "사이드는 치즈스틱으로 바꿀게요")
    assert r.detected_language == "ko"
    main = r.intents[0]
    assert main.item_id == "burger_bulgogi"
    assert main.is_set is True
    assert main.drink_id == "drink_cola"
    assert main.drink_size == "L"
    assert main.side_id == "side_cheese_stick"


def test_nlu_multiple_items():
    r = parse_order("더블 치즈버거 두개랑 콜라 주세요")
    ids = {it.item_id for it in r.intents}
    assert "burger_double_cheese" in ids
    assert "drink_cola" in ids               # 음료도 별도로 담김


def test_nlu_english_detection():
    r = parse_order("I want a shrimp burger set and a large cola")
    assert r.detected_language == "en"
    assert r.intents[0].item_id == "burger_shrimp"
    assert r.intents[0].is_set is True


# ──────────────────────────────────────────────
# pytest 없이 직접 실행할 때
# ──────────────────────────────────────────────
def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in tests:
        try:
            fn()
            print(f"  [PASS] {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {fn.__name__}: {e}")
        except Exception as e:
            print(f"  [ERR ] {fn.__name__}: {e}")
    print(f"\n결과: {passed}/{len(tests)} 통과")
    return passed == len(tests)


if __name__ == "__main__":
    print("===== 유니버셜 키오스크 핵심 기능 검증 =====")
    ok = _run_all()
    sys.exit(0 if ok else 1)
