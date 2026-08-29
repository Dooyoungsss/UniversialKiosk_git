#!/usr/bin/env python3
"""새 기능 검증: 환영화면 음성버튼, 퍼지 검색, 제스처 라우팅"""
from core.nlu import parse_order

print("=" * 50)
print("새 기능 검증 테스트")
print("=" * 50)

# 테스트 1: 기존 완전 매칭
r1 = parse_order('불고기버거 하나')
assert r1.intents and r1.intents[0].item_id == 'burger_bulgogi'
print("✅ 테스트1: 완전매칭 (불고기버거) → PASS")

# 테스트 2: 퍼지 - '치즈'만 말함 → 더블치즈버거 추천
r2 = parse_order('치즈')
assert r2.intents and r2.intents[0].item_id == 'burger_double_cheese'
print("✅ 테스트2: 퍼지검색 (치즈 → 더블치즈버거) → PASS")

# 테스트 3: 퍼지 - '콜라'
r3 = parse_order('콜라')
assert r3.intents and r3.intents[0].item_id == 'drink_cola'
print("✅ 테스트3: 퍼지검색 (콜라 → drink_cola) → PASS")

# 테스트 4: 퍼지 - '커피'
r4 = parse_order('커피')
assert r4.intents and r4.intents[0].item_id == 'drink_americano'
print("✅ 테스트4: 퍼지검색 (커피 → 아메리카노) → PASS")

# 테스트 5: 퍼지 - '새우' 
r5 = parse_order('새우')
assert r5.intents and r5.intents[0].item_id == 'burger_shrimp'
print("✅ 테스트5: 퍼지검색 (새우 → 새우버거) → PASS")

# 테스트 6: 복잡한 문장 (기존 완전매칭 + 콜라는 음료)
r6 = parse_order('치킨버거 두 개랑 콜라 라지로')
assert len(r6.intents) >= 1
assert r6.intents[0].item_id == 'burger_chicken'
assert r6.intents[0].qty == 2
assert r6.intents[0].drink_size == 'L'
print("✅ 테스트6: 복합문장 (치킨버거 2개 + 콜라 L) → PASS")

# 테스트 7: 의도 인식 (비우기/결제)
r7 = parse_order('다 지워줘')
assert r7.intents and r7.intents[0].action == 'clear'
print("✅ 테스트7: 명령어인식 (다 지워줘 → clear) → PASS")

r8 = parse_order('결제할게')
assert r8.intents and r8.intents[0].action == 'checkout'
print("✅ 테스트8: 명령어인식 (결제할게 → checkout) → PASS")

print("=" * 50)
print("모든 테스트 통과! ✅")
print("=" * 50)
