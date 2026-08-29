"""
core/menu_data.py — 햄버거 매장 메뉴 데이터
================================================
계획서의 "햄버거 매장 시뮬레이션"을 위한 실제 메뉴 정보입니다.
각 메뉴는 한국어/영어 이름을 모두 갖고 있어 다국어 전환이 가능합니다.

객체 지향 프로그래밍(OOP) 학습 요소:
  - MenuItem  : 메뉴 1개를 표현하는 클래스
  - 메뉴 데이터, 사용자 세션, DB 를 각각 독립 클래스로 분리(계획서 4.3 참고)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# 메뉴 분류(카테고리)
CATEGORY_BURGER = "burger"
CATEGORY_SIDE = "side"
CATEGORY_DRINK = "drink"

CATEGORY_LABELS = {
    "ko": {CATEGORY_BURGER: "버거", CATEGORY_SIDE: "사이드", CATEGORY_DRINK: "음료"},
    "en": {CATEGORY_BURGER: "Burger", CATEGORY_SIDE: "Side", CATEGORY_DRINK: "Drink"},
    "zh": {CATEGORY_BURGER: "汉堡", CATEGORY_SIDE: "配菜", CATEGORY_DRINK: "饮料"},
}
CATEGORY_ORDER = [CATEGORY_BURGER, CATEGORY_SIDE, CATEGORY_DRINK]


@dataclass
class MenuItem:
    """메뉴 한 개를 표현하는 클래스."""
    item_id: str
    name_ko: str
    name_en: str
    price: int
    category: str
    emoji: str                       # 이미지 대신 사용하는 큰 그림문자(어디서나 잘 보임)
    is_best: bool = False            # 베스트셀러 여부(실버 모드에서 우선 노출)
    keywords: list[str] = field(default_factory=list)  # 자연어 주문 매칭용 단어들
    name_zh: str = ""                 # 중국어 이름(비워두면 영어 이름으로 대체)

    def name(self, lang: str = "ko") -> str:
        """언어에 맞는 이름을 돌려줍니다."""
        if lang == "en":
            return self.name_en
        if lang == "zh":
            return self.name_zh or self.name_en
        return self.name_ko


# ──────────────────────────────────────────────
# 전체 메뉴 목록
# ──────────────────────────────────────────────
MENU: list[MenuItem] = [
    # ── 버거 ──
    MenuItem("burger_double_cheese", "더블 치즈버거", "Double Cheeseburger", 6500,
             CATEGORY_BURGER, "🍔", is_best=True,
             keywords=["더블치즈", "더블 치즈", "치즈버거", "double cheese", "cheeseburger",
                       "双层苝士", "苝士堡", "苝士汉堡"],
             name_zh="双层苝士汉堡"),
    MenuItem("burger_bulgogi", "불고기버거", "Bulgogi Burger", 5500,
             CATEGORY_BURGER, "🍔", is_best=True,
             keywords=["불고기", "bulgogi", "烤肉"], name_zh="烤肉汉堡"),
    MenuItem("burger_shrimp", "새우버거", "Shrimp Burger", 5800,
             CATEGORY_BURGER, "🍤", is_best=True,
             keywords=["새우", "shrimp", "鲜虾", "虾"], name_zh="鲜虾汉堡"),
    MenuItem("burger_chicken", "치킨버거", "Chicken Burger", 5200,
             CATEGORY_BURGER, "🍗", is_best=True,
             keywords=["치킨버거", "치킨 버거", "chicken burger", "鸡肉汉堡", "鸡肉堡"],
             name_zh="鸡肉汉堡"),
    MenuItem("burger_big", "빅버거", "Big Burger", 7200,
             CATEGORY_BURGER, "🍔",
             keywords=["빅버거", "빅 버거", "big burger", "大汉堡"], name_zh="大汉堡"),
    MenuItem("burger_hanwoo", "한우버거", "Hanwoo Beef Burger", 9800,
             CATEGORY_BURGER, "🥩",
             keywords=["한우", "hanwoo", "beef", "韩牛", "牛肉汉堡"], name_zh="韩牛汉堡"),

    # ── 사이드 ──
    MenuItem("side_fries", "감자튀김", "French Fries", 2500,
             CATEGORY_SIDE, "🍟", is_best=True,
             keywords=["감자튀김", "감자", "후라이", "프렌치프라이", "fries", "french fries",
                       "薯条", "炸薯条"],
             name_zh="薯条"),
    MenuItem("side_cheese_stick", "치즈스틱", "Cheese Stick", 3000,
             CATEGORY_SIDE, "🧀",
             keywords=["치즈스틱", "치즈 스틱", "cheese stick", "苝士棒"], name_zh="苝士棒"),
    MenuItem("side_nugget", "치킨너겟", "Chicken Nuggets", 3200,
             CATEGORY_SIDE, "🍗",
             keywords=["너겟", "치킨너겟", "nugget", "nuggets", "鸡块"], name_zh="鸡块"),
    MenuItem("side_corn", "콘샐러드", "Corn Salad", 2200,
             CATEGORY_SIDE, "🌽",
             keywords=["콘샐러드", "콘 샐러드", "corn", "corn salad", "玉米沙拉", "玉米"],
             name_zh="玉米沙拉"),

    # ── 음료 ──
    MenuItem("drink_cola", "콜라", "Cola", 2000,
             CATEGORY_DRINK, "🥤", is_best=True,
             keywords=["콜라", "코카콜라", "cola", "coke", "可乐"], name_zh="可乐"),
    MenuItem("drink_cider", "사이다", "Cider", 2000,
             CATEGORY_DRINK, "🥤",
             keywords=["사이다", "cider", "sprite", "雪碧", "汽水"], name_zh="雪碧"),
    MenuItem("drink_americano", "아메리카노", "Americano", 2800,
             CATEGORY_DRINK, "☕",
             keywords=["아메리카노", "커피", "americano", "coffee", "美式", "咖啡"],
             name_zh="美式咖啡"),
    MenuItem("drink_orange", "오렌지주스", "Orange Juice", 2500,
             CATEGORY_DRINK, "🧃",
             keywords=["오렌지", "주스", "오렌지주스", "orange", "juice", "橙汁", "果汁"],
             name_zh="橙汁"),
]

# 빠른 조회용 사전(아이디 → 메뉴)
MENU_BY_ID: dict[str, MenuItem] = {m.item_id: m for m in MENU}


def get_item(item_id: str) -> Optional[MenuItem]:
    """아이디로 메뉴를 찾습니다."""
    return MENU_BY_ID.get(item_id)


def items_in_category(category: str) -> list[MenuItem]:
    """특정 카테고리의 메뉴만 골라 돌려줍니다."""
    return [m for m in MENU if m.category == category]


def best_sellers() -> list[MenuItem]:
    """베스트셀러 메뉴만 돌려줍니다(실버 모드에서 4종 전면 노출에 사용)."""
    return [m for m in MENU if m.is_best]


# ──────────────────────────────────────────────
# 음료 사이즈 / 세트 옵션
# ──────────────────────────────────────────────
DRINK_SIZES = {
    "ko": {"M": "미디엄", "L": "라지"},
    "en": {"M": "Medium", "L": "Large"},
    "zh": {"M": "中杯", "L": "大杯"},
}
SIZE_EXTRA_PRICE = {"M": 0, "L": 500}     # 라지 사이즈 추가요금

SET_EXTRA_PRICE = 2700                     # 단품 → 세트 변경 시 추가요금(사이드+음료)
