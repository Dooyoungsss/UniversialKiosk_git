"""
core/nlu.py — 자연어 주문 분석기 (음성 주문 · 다국어)
================================================
사용자가 말한(또는 입력한) 문장을 분석해 '장바구니 명령' 으로 바꿉니다.

· 인터넷·API 키 없이 항상 동작하는 오프라인 규칙(룰) 기반 분석기입니다.
  → 대회장 네트워크 상태와 상관없이 같은 결과를 내도록 안정성을 우선했습니다.
· 한국어 · 영어 · 중국어 문장을 모두 이해하고, 문장 언어를 감지해
  화면 언어를 자동으로 바꿀 수 있게 알려줍니다.

예) "불고기버거 세트 하나 주시는데 음료는 콜라 라지로 바꾸고
     사이드는 치즈스틱으로 바꿀게요"
  → [{action:add, item_id:burger_bulgogi, qty:1, is_set:true,
       drink:drink_cola, drink_size:L, side:side_cheese_stick}]
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from core import menu_data


# ──────────────────────────────────────────────
# 분석 결과를 담는 자료구조
# ──────────────────────────────────────────────
@dataclass
class OrderIntent:
    """문장 하나에서 뽑아낸 '하나의 주문 의도'."""
    # add(담기) / remove(빼기) / show_cart(담은 메뉴 알려주기) / clear(비우기) / checkout(결제)
    action: str = "add"
    item_id: Optional[str] = None
    qty: int = 1
    is_set: bool = False
    drink_id: Optional[str] = None    # 세트 음료 교체
    drink_size: str = "M"
    side_id: Optional[str] = None     # 세트 사이드 교체


@dataclass
class NLUResult:
    intents: list[OrderIntent] = field(default_factory=list)
    detected_language: str = "ko"     # 감지한 언어(ko/en/zh)


# 한국어 수량 표현
# · 카운터(개/잔/세트…)와 함께 쓰는 1글자 수사: "두 개", "세 잔"
_KO_NUM_COUNTER = {
    "한": 1, "두": 2, "세": 3, "네": 4,
    "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10,
}
# · 카운터 없이 단독으로 써도 뜻이 분명한 수사: "버거 하나", "둘"
_KO_NUM_STANDALONE = {
    "하나": 1, "둘": 2, "셋": 3, "넷": 4,
    "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10,
}
# · 영어 수사(메뉴 앞에 옴): "two burgers"
_EN_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
# · 중국어 수사(메뉴 앞에 옴): "两个汉堡", "一份套餐"
_ZH_NUM = {
    "一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}
_ZH_COUNTER = "个|份|杯|块|套|瓶|盒"
# 수량 뒤에 붙는 단위(카운터)
_COUNTER = "개|잔|컵|봉|조각|세트|set"

# '○○ 빼줘' — 메뉴를 장바구니에서 뺌. '피클 빼고 주세요'의 '빼고'는 빼기 요청이 아니므로 제외
_REMOVE_RE = re.compile(r"빼\s*(?:줘|주|요|라|버|$)|뺄|뺐|제거|삭제|없애|취소|"
                        r"\bremove\b|\bdelete\b|take (?:it )?(?:out|off)|\bcancel\b|"
                        r"去掉|删掉|删除|不要了|拿掉|取消")
# 세트 구성 바꾸기('감자튀김 빼고 치즈스틱으로 바꿔줘')는 빼기가 아님
_CHANGE_WORDS = ("바꿔", "변경", "대신", "change", "instead", "换", "改")
# '고른 메뉴 보여줘' — 담은 메뉴와 합계를 알려 줌
_SHOW_WORDS = ("뭐 담", "뭘 담", "뭐가 담", "무엇을 담", "뭐 골랐", "뭘 골랐", "뭐 시켰", "뭘 시켰",
               "뭐 주문", "뭘 주문", "담은 메뉴", "담은 거", "담긴 메뉴", "담긴 거", "고른 메뉴",
               "고른 거", "주문한 메뉴", "주문한 거", "주문 내역", "주문내역", "장바구니",
               "what's in my cart", "what is in my cart", "my cart", "my order",
               "what did i order", "what i ordered",
               "购物车", "我点了什么", "点了什么", "我的订单", "已点")
# 메뉴 이름과 함께 '장바구니'라고 하면 담기일 수도 있으므로, 이런 말이 있을 때만 알려주기로 봄
_SHOW_VERBS = ("보여", "알려", "읽어", "확인", "뭐", "뭘", "무엇", "what", "show", "read", "tell",
               "check", "看", "什么")


def detect_language(text: str) -> str:
    """문장 언어를 간단 판별합니다.

    · 한글(가-힣)이 있으면 한국어("ko")
    · 한글은 없고 한자(CJK)가 있으면 중국어("zh")
    · 둘 다 없으면 영어("en")
    """
    if re.search(r"[가-힣]", text):
        return "ko"
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh"
    return "en"


# ──────────────────────────────────────────────
# 메인 진입점
# ──────────────────────────────────────────────
def parse_order(text: str) -> NLUResult:
    """자연어 주문 문장을 분석합니다(오프라인 규칙 기반)."""
    text = (text or "").strip()
    if not text:
        return NLUResult()
    return _parse_with_rules(text)


# ──────────────────────────────────────────────
# 오프라인 룰 기반 분석기 — 인터넷 없이 항상 동작
# ──────────────────────────────────────────────
def _find_menu_in_text(text: str, category: Optional[str] = None):
    """문장 안에서 메뉴 키워드를 찾아 (MenuItem, 매칭위치) 목록을 돌려줍니다."""
    low = text.lower()
    found = []
    for item in menu_data.MENU:
        if category and item.category != category:
            continue
        for kw in item.keywords:
            pos = low.find(kw.lower())
            if pos >= 0:
                found.append((item, pos))
                break
    found.sort(key=lambda t: t[1])     # 문장에 나온 순서대로 정렬
    return found


def _find_menu_fuzzy(text: str):
    """부분 문자열 퍼지 검색 — 기존 키워드 검색이 실패했을 때 폴백으로 씁니다.

    예) "치즈" → 키워드에 '치즈'가 없어도 name_ko '더블 치즈버거'에 포함되므로 매칭.
    베스트셀러(is_best=True)에 보너스를 줘서, 동점이면 인기 메뉴를 우선 추천합니다.
    """
    low = text.lower()
    # 공백·구두점으로 분리한 토큰 중 2글자 이상만 의미 있음
    tokens = [w for w in re.split(r'[\s,.?!]+', low) if len(w) >= 2]
    if not tokens:
        tokens = [low]

    found = []
    for item in menu_data.MENU:
        targets = (
            [item.name_ko.lower(), item.name_en.lower()]
            + [kw.lower() for kw in item.keywords]
        )
        if item.name_zh:
            targets.append(item.name_zh.lower())

        best_score = 0.0
        for token in tokens:
            for target in targets:
                if token in target and len(target) > 0:
                    ratio = len(token) / len(target)
                    best_score = max(best_score, ratio)

        if best_score > 0:
            score = int(best_score * 100) + (50 if item.is_best else 0)
            found.append((item, score))

    found.sort(key=lambda t: -t[1])
    return found


def _extract_qty(text: str, around: int, default: int = 1) -> int:
    """메뉴 키워드 주변에서 수량을 찾습니다.

    한국어는 수량이 메뉴 '뒤'에 오고(예: "버거 두 개"),
    영어·중국어는 메뉴 '앞'에 옵니다(예: "two burgers", "两个汉堡").
    부분일치 오인('세트'의 '세'=3, '한우'의 '한'=1)과
    옆 메뉴 수량 전염을 막기 위해 카운터·단독수사·앞숫자를 구분해 처리합니다.
    """
    low = text.lower()
    after = text[around: around + 14]          # 키워드 뒤쪽(한국어 수량)
    before = low[max(0, around - 10): around]  # 키워드 앞쪽(영어/중국어/숫자 수량)

    # 1) 메뉴 바로 앞의 숫자/영어·중국어 수사 (예: "2 burgers", "two burgers", "两个汉堡")
    m = re.search(r"(\d+)\s*$", before)
    if m:
        return max(1, int(m.group(1)))
    for word, n in _EN_NUM.items():
        if re.search(rf"\b{word}\b\s*$", before):
            return n
    m = re.search(rf"([一两二三四五六七八九十])\s*(?:{_ZH_COUNTER})?\s*$", before)
    if m:
        return _ZH_NUM[m.group(1)]

    # 2) 메뉴 뒤의 숫자 (+선택 카운터) (예: "버거 3개")
    m = re.search(rf"(\d+)\s*(?:{_COUNTER})?", after)
    if m:
        return max(1, int(m.group(1)))

    # 3) 한글 수사 + 카운터 (예: "두 개" → 2). '세트'의 '세'는 카운터가 안 붙어 제외됨
    m = re.search(rf"(한|두|세|네|다섯|여섯|일곱|여덟|아홉|열)\s*(?:{_COUNTER})", after)
    if m:
        return _KO_NUM_COUNTER[m.group(1)]

    # 4) 단독으로 뜻이 분명한 한글 수사 (예: "버거 하나")
    for word, n in _KO_NUM_STANDALONE.items():
        if word in after:
            return n
    return default


def _parse_with_rules(text: str) -> NLUResult:
    """규칙 기반 자연어 분석(핵심 차별화 로직)."""
    lang = detect_language(text)
    result = NLUResult(detected_language=lang)
    low = text.lower()

    # '○○ 빼줘': 메뉴 이름이 있으면 그 메뉴만 뺌('콜라 취소해줘'가 장바구니 전체를 비우지 않게)
    if _REMOVE_RE.search(low.rstrip(" .!?。！？")) and not any(k in low for k in _CHANGE_WORDS):
        found = _find_menu_in_text(text)
        if not found:
            fuzzy = _find_menu_fuzzy(text)
            found = [(fuzzy[0][0], 0)] if fuzzy else []
        if found:
            set_said = any(k in low for k in ["세트", "set", "combo", "套餐"])
            for item, pos in found:
                result.intents.append(OrderIntent(
                    action="remove", item_id=item.item_id,
                    qty=_extract_qty(text, pos, default=0),     # 0 = 그 메뉴 모두
                    is_set=set_said and item.category == menu_data.CATEGORY_BURGER))
            return result

    # 전체 비우기 / 결제 의도 먼저 확인
    if any(k in low for k in ["다 지워", "전부 삭제", "비워", "취소", "clear", "empty",
                              "清空", "删除", "全部删", "取消"]):
        result.intents.append(OrderIntent(action="clear"))
        return result
    # '결재'는 맞춤법은 다르지만 음성 인식이 '결제'를 '결재'로 받아 적는 경우가 많아 함께 인정
    if any(k in low for k in ["결제", "결재", "주문 완료", "계산", "checkout", "check out", "pay",
                              "that's all", "that is all", "그게 다", "끝",
                              "结账", "结算", "付款", "买单"]):
        result.intents.append(OrderIntent(action="checkout"))
    elif any(k in low for k in _SHOW_WORDS) and (
            not _find_menu_in_text(text) or any(v in low for v in _SHOW_VERBS)):
        # '고른 메뉴 보여줘'·'뭐 담았어?' — 담은 메뉴를 알려 줌(결제 요청이면 결제 확인 때 읽어 줌)
        result.intents.append(OrderIntent(action="show_cart"))
        return result

    is_set = any(k in low for k in ["세트", "set", "combo", "套餐"])
    drink_size = "L" if any(k in low for k in ["라지", "큰", "large", "라쥐", "大杯", "大号"]) else "M"

    # 세트 음료/사이드 교체 감지
    drink_override = None
    for d in _find_menu_in_text(text, menu_data.CATEGORY_DRINK):
        drink_override = d[0].item_id
        break
    side_override = None
    if any(k in low for k in ["사이드", "바꿔", "변경", "대신", "change", "instead",
                              "换", "改", "配菜"]):
        for s in _find_menu_in_text(text, menu_data.CATEGORY_SIDE):
            side_override = s[0].item_id
            break

    burgers = _find_menu_in_text(text, menu_data.CATEGORY_BURGER)
    sides = _find_menu_in_text(text, menu_data.CATEGORY_SIDE)
    drinks = _find_menu_in_text(text, menu_data.CATEGORY_DRINK)

    if burgers:
        # 버거가 중심이 되는 주문(세트 옵션을 버거에 부착)
        for item, pos in burgers:
            result.intents.append(OrderIntent(
                action="add", item_id=item.item_id,
                qty=_extract_qty(text, pos), is_set=is_set,
                drink_id=drink_override if is_set else None,
                drink_size=drink_size,
                side_id=side_override if is_set else None,
            ))
        # 세트가 아니라면, 함께 말한 음료/사이드는 '별도 단품'으로 추가합니다.
        # (예: "더블 치즈버거 두개랑 콜라 주세요")
        if not is_set:
            for item, pos in sides + drinks:
                size = drink_size if item.category == menu_data.CATEGORY_DRINK else "M"
                result.intents.append(OrderIntent(
                    action="add", item_id=item.item_id,
                    qty=_extract_qty(text, pos), drink_size=size))
    else:
        # 버거 없이 사이드/음료만 주문하는 경우
        for item, pos in sides + drinks:
            size = drink_size if item.category == menu_data.CATEGORY_DRINK else "M"
            result.intents.append(OrderIntent(
                action="add", item_id=item.item_id,
                qty=_extract_qty(text, pos), drink_size=size))

    # ── 퍼지 폴백: 키워드 검색으로 아무 메뉴도 못 찾았을 때 ──
    # 예) "치즈" → 더블 치즈버거(is_best), "새우" → 새우버거, "커피" → 아메리카노
    if not any(i.item_id for i in result.intents):
        fuzzy = _find_menu_fuzzy(text)
        if fuzzy:
            top = fuzzy[0][0]
            result.intents.append(OrderIntent(
                action="add", item_id=top.item_id,
                qty=_extract_qty(text, 0),
                is_set=is_set,
                drink_size=drink_size,
            ))

    return result
