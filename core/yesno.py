"""
core/yesno.py — '네/아니요' 대답 판별(한국어·영어·중국어)
================================================
시각장애인 안내창의 '눈이 불편하신가요?'와 음성 주문의 '결제할까요?' 질문에 대한
대답을 판별합니다. 짧은 대답은 음성 인식기가 여러 후보를 내므로, 후보들을
' / ' 로, 언어별 결과를 ' || ' 로 이어 붙인 문자열을 받아 앞쪽부터 판단합니다.
"""
from __future__ import annotations

import re

# 영어는 'no'가 'cannot' 안에도 들어 있으므로 낱말 단위로만 비교합니다.
YES_KO_ZH = ("맞아", "맞어", "맞습니다", "네", "내", "넵", "넹", "예", "응", "그래", "당연",
             "시각장애", "장애", "도와", "그렇", "좋아", "안 보", "안보", "잘 안",
             "是", "对", "好", "嗯", "需要", "看不清")
YES_EN = ("yes", "yeah", "yep", "yup", "correct", "sure", "okay", "ok", "please")
YES_EN_PHRASE = ("can't see", "cannot see", "can not see")
NO_KO_ZH = ("아니", "아뇨", "괜찮", "됐어", "됐습니다", "不", "沒", "没", "不用")
# 'nah' 는 넣지 않음: 영어 인식기가 한국어 '네'를 'nah'로 받아 적는 일이 많음
NO_EN = ("no", "nope")
# '괜찮네요'처럼 두 쪽이 섞였을 때 '네'로 볼 분명한 도움 요청
STRONG_YES = ("안 보", "안보", "잘 안", "시각장애", "도와", "看不清", "can't see", "cannot see")

LANG_SEP = " || "     # 언어별 인식 결과 구분
ALT_SEP = " / "       # 같은 언어의 인식 후보 구분


def _en_words(t: str) -> set[str]:
    return set(re.findall(r"[a-z']+", t))


def is_affirmative(text: str) -> bool:
    """'네'에 해당하는 대답인지(한/영/중) 판별."""
    t = (text or "").strip().lower()
    if not t:
        return False
    if any(w in t for w in YES_KO_ZH + YES_EN_PHRASE):
        return True
    return bool(_en_words(t) & set(YES_EN))


def is_negative(text: str) -> bool:
    """'아니요'에 해당하는 대답인지(한/영/중) 판별."""
    t = (text or "").strip().lower()
    if not t:
        return False
    if any(w in t for w in NO_KO_ZH):
        return True
    return bool(_en_words(t) & set(NO_EN))


def _answer_one(text: str):
    yes, no = is_affirmative(text), is_negative(text)
    if yes and not no:
        return True
    if no and not yes:
        return False
    if yes and no:
        t = (text or "").lower()
        return any(w in t for w in STRONG_YES)
    return None


def yes_no_answer(text: str):
    """들은 말이 '네'면 True, '아니요'면 False, 판단할 수 없으면 None.

    여러 언어로 인식한 결과(' || ' 로 구분)는 앞쪽 언어부터 보고, 처음으로 분명한
    대답이 나온 언어를 따릅니다. (화면이 영어여도 한국어 '네'를 알아들음)
    """
    for part in (text or "").split(LANG_SEP):
        ans = _answer_one(part)
        if ans is not None:
            return ans
    return None


def first_transcript(text: str) -> str:
    """여러 언어·후보를 이어 붙인 인식 결과에서 화면에 보여 줄 첫 후보만 꺼냅니다."""
    return (text or "").split(LANG_SEP)[0].split(ALT_SEP)[0].strip()
