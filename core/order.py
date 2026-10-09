"""
core/order.py — 장바구니 / 주문 세션 (OOP)
================================================
계획서 4.3: "햄버거 메뉴 데이터, 사용자 속성 세션, DB 인터페이스를
독립적인 클래스로 설계" → 그중 '주문/세션' 클래스를 담당합니다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core import menu_data
from core.menu_data import MenuItem


@dataclass
class CartLine:
    """장바구니에 담긴 한 줄(메뉴 + 수량 + 옵션)."""
    item: MenuItem
    qty: int = 1
    is_set: bool = False             # 세트 여부(사이드+음료 포함)
    drink_size: str = "M"            # 음료 사이즈(M/L)
    note: str = ""                   # 옵션 메모(예: "음료를 콜라로 변경")
    drink_id: str | None = None      # 세트에서 고른 음료(표시용, 추가요금 없음)
    side_id: str | None = None       # 세트에서 고른 사이드(표시용, 추가요금 없음)

    def unit_price(self) -> int:
        """이 줄의 1개당 가격(세트/사이즈 추가요금 포함).

        사이즈 추가요금은 '음료' 이거나 '세트'(음료 포함)일 때만 붙습니다.
        → 단품 버거가 '라지' 라는 말 때문에 잘못 비싸지는 일을 막습니다.
        세트의 음료·사이드 '종류 변경' 자체는 추가요금이 없습니다(세트 정가).
        """
        price = self.item.price
        if self.is_set:
            price += menu_data.SET_EXTRA_PRICE
        if self.is_set or self.item.category == menu_data.CATEGORY_DRINK:
            price += menu_data.SIZE_EXTRA_PRICE.get(self.drink_size, 0)
        return price

    def line_total(self) -> int:
        """이 줄의 합계 금액."""
        return self.unit_price() * self.qty

    def describe(self, lang: str = "ko") -> str:
        """사람이 읽기 좋은 설명 문자열."""
        name = self.item.name(lang)
        parts = [name]
        if self.is_set:
            set_word = {"ko": "세트", "en": "Set", "zh": "套餐"}.get(lang, "Set")
            parts.append(set_word)
            extras = []
            if self.drink_id:
                d = menu_data.get_item(self.drink_id)
                if d:
                    dn = d.name(lang)
                    if self.drink_size == "L":
                        dn += f"({menu_data.DRINK_SIZES[lang]['L']})"
                    extras.append(dn)
            if self.side_id:
                s = menu_data.get_item(self.side_id)
                if s:
                    extras.append(s.name(lang))
            if extras:
                parts.append("· " + " · ".join(extras))
        elif self.item.category == menu_data.CATEGORY_DRINK and self.drink_size == "L":
            parts.append(menu_data.DRINK_SIZES[lang]["L"])
        return " ".join(parts)


class Cart:
    """장바구니 전체를 관리하는 클래스."""

    def __init__(self):
        self.lines: list[CartLine] = []

    def add(self, item: MenuItem, qty: int = 1, is_set: bool = False,
            drink_size: str = "M", note: str = "",
            drink_id: str | None = None, side_id: str | None = None) -> None:
        """메뉴를 담습니다. 같은 메뉴/옵션이면 수량만 늘립니다."""
        for line in self.lines:
            if (line.item.item_id == item.item_id and line.is_set == is_set
                    and line.drink_size == drink_size
                    and line.drink_id == drink_id and line.side_id == side_id):
                line.qty += qty
                return
        self.lines.append(CartLine(item, qty, is_set, drink_size, note,
                                   drink_id, side_id))

    def remove_index(self, idx: int) -> None:
        if 0 <= idx < len(self.lines):
            self.lines.pop(idx)

    def change_qty(self, idx: int, delta: int) -> None:
        """수량을 늘리거나(+) 줄입니다(-). 0 이 되면 삭제합니다."""
        if 0 <= idx < len(self.lines):
            self.lines[idx].qty += delta
            if self.lines[idx].qty <= 0:
                self.lines.pop(idx)

    def clear(self) -> None:
        self.lines.clear()

    def total(self) -> int:
        return sum(line.line_total() for line in self.lines)

    def item_count(self) -> int:
        return sum(line.qty for line in self.lines)

    def is_empty(self) -> bool:
        return len(self.lines) == 0

    def to_records(self) -> list[dict]:
        """DB 통계 저장용 간단한 딕셔너리 목록으로 변환."""
        return [
            {"id": l.item.item_id, "name": l.item.name_ko,
             "qty": l.qty, "is_set": l.is_set, "price": l.line_total()}
            for l in self.lines
        ]
