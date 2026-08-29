"""
core/regulars.py — 익명 단골 매칭 매니저 (계획서 2.2)
================================================
얼굴 임베딩 벡터를 받아 DB 의 단골들과 코사인 유사도로 비교하여,
"이 사람이 단골인지, 누구인지"를 1초 안에 판별합니다.

오인식 방지: 한 프레임만 보고 단정하지 않고, 연속으로 N번 같은 사람이
나와야 '단골 확정' 으로 처리합니다(FACE_MATCH_STABLE_FRAMES).
"""
from __future__ import annotations

import time
from typing import Optional

import numpy as np

import config
from config import (FACE_MATCH_THRESHOLD_PROJECTED, FACE_MATCH_THRESHOLD_STRICT,
                    FACE_MATCH_STABLE_FRAMES, FACE_REF_MIN_SAMPLES)
from core.database import KioskDatabase
from core.mathutils import cosine_similarity, normalize_vector


class RegularManager:
    """단골 등록·인식을 담당하는 클래스."""

    def __init__(self, db: KioskDatabase):
        self.db = db
        self._regulars = db.get_all_regulars()      # 메모리에 캐시
        self._stable_id: Optional[int] = None       # 연속 매칭 중인 후보
        self._stable_count = 0
        self._announced_id: Optional[int] = None    # 이미 '환영'한 단골(중복 인사 방지)

        # ── '평균 얼굴' 기준 누적(개인차만 비교하기 위한 핵심 장치) ──
        # 모든 얼굴이 공유하는 공통 성분을 빼야 서로 다른 사람을 구별할 수 있습니다.
        # 등록된 단골들 + 카메라가 본 얼굴들을 모아 평균을 만들고, 비교 직전에
        # 양쪽에서 이 평균을 빼서 '그 사람만의 차이'로 닮음을 측정합니다.
        self._ref_sum: np.ndarray = np.zeros(0)
        self._ref_count = 0
        self._dbg_last = 0.0                         # 진단 로그 throttle
        for reg in self._regulars:                  # 기존 단골로 기준을 초기 시드
            self._accumulate(reg["embedding"])

    def reload(self) -> None:
        """DB 가 바뀌면 캐시를 다시 불러옵니다."""
        self._regulars = self.db.get_all_regulars()

    # ──────────────────────────────────────────
    # '평균 얼굴' 기준 관리 (개인차만 비교하기 위함)
    # ──────────────────────────────────────────
    def _accumulate(self, embedding: np.ndarray) -> bool:
        """정상 범위(단위벡터에 가까운)의 얼굴 임베딩만 기준 평균에 더합니다.

        테스트나 시뮬레이션이 만든 비정상 벡터(크기가 1과 크게 다른 값)는
        평균을 망치므로 제외합니다.
        """
        emb = np.asarray(embedding, dtype=np.float64)
        norm = float(np.linalg.norm(emb))
        if emb.size == 0 or not (0.5 < norm < 2.0):
            return False
        if self._ref_sum.shape[0] != emb.shape[0]:   # 차원이 다르면 초기화
            self._ref_sum = np.zeros(emb.shape[0])
            self._ref_count = 0
        self._ref_sum += emb
        self._ref_count += 1
        return True

    def observe(self, embedding: np.ndarray) -> None:
        """카메라가 본 얼굴을 기준 평균에 반영합니다(손님 1명당 한 번 권장)."""
        self._accumulate(embedding)

    def _reference(self) -> Optional[np.ndarray]:
        """충분한 표본이 모였을 때만 '평균 얼굴' 벡터를 돌려줍니다."""
        if self._ref_count >= FACE_REF_MIN_SAMPLES and self._ref_sum.shape[0] > 0:
            return self._ref_sum / self._ref_count
        return None

    def _project(self, embedding: np.ndarray) -> np.ndarray:
        """공통 '평균 얼굴' 성분을 빼고 개인차만 남긴 비교용 벡터.

        기준이 아직 없으면(표본 부족) 원본을 그대로 씁니다.
        """
        emb = np.asarray(embedding, dtype=np.float64)
        ref = self._reference()
        if ref is None or ref.shape[0] != emb.shape[0]:
            return emb
        diff = emb - ref
        if float(np.linalg.norm(diff)) < 1e-6:        # 기준과 거의 같으면 식별 불가
            return np.zeros_like(diff)
        return normalize_vector(diff)

    # ──────────────────────────────────────────
    # 인식
    # ──────────────────────────────────────────
    def best_match(self, embedding: np.ndarray) -> tuple[Optional[dict], float]:
        """현재 얼굴과 가장 닮은 단골과 그 유사도를 돌려줍니다.

        '평균 얼굴' 성분을 뺀 개인차끼리 코사인 유사도를 비교하므로,
        서로 다른 사람을 같은 단골로 오인식하지 않습니다.
        """
        query = self._project(embedding)
        best, best_sim = None, -1.0
        for reg in self._regulars:
            sim = cosine_similarity(query, self._project(reg["embedding"]))
            if sim > best_sim:
                best, best_sim = reg, sim
        return best, best_sim

    def recognize(self, embedding: np.ndarray) -> Optional[dict]:
        """프레임마다 호출. 연속으로 안정적으로 일치하면 단골을 확정 반환."""
        if not self._regulars:
            return None
        match, sim = self.best_match(embedding)
        ref_active = self._reference() is not None
        # 기준(평균 얼굴)을 빼고 비교 중이면 개인차 공간 전용 임계값(0.70)을 쓰고,
        # 기준이 아직 없으면(표본 부족) '거의 똑같은 얼굴(0.999)' 만 같은 사람으로 인정합니다.
        # → 기준이 없어도 서로 다른 사람(코사인 0.95~0.99)이 단골로 오인식되지 않습니다.
        threshold = (FACE_MATCH_THRESHOLD_PROJECTED if ref_active
                     else FACE_MATCH_THRESHOLD_STRICT)
        if config.FACE_DEBUG and config.VISION_ENABLED:
            self._debug_log(embedding, match, sim, ref_active, threshold)
        if match and sim >= threshold:
            if self._stable_id == match["id"]:
                self._stable_count += 1
            else:
                self._stable_id = match["id"]
                self._stable_count = 1
            # 충분히 안정적으로 일치하면 확정하되, 한 번 인사한 단골은
            # 추적이 끊기기 전까지 다시 반환하지 않습니다(환영 대화상자가
            # 매 프레임 중복으로 뜨는 것을 근본적으로 막음).
            if (self._stable_count >= FACE_MATCH_STABLE_FRAMES
                    and self._announced_id != match["id"]):
                self._announced_id = match["id"]
                return match
        else:
            self._stable_id = None
            self._stable_count = 0
        return None

    def _debug_log(self, embedding, match, sim, ref_active, threshold) -> None:
        """실제 얼굴의 원본/보정 코사인 값을 1초에 한 번 콘솔에 찍어 원인 진단."""
        now = time.time()
        if now - self._dbg_last < 1.0:
            return
        self._dbg_last = now
        raw_best, raw_sim = None, -1.0
        for reg in self._regulars:
            c = cosine_similarity(embedding, np.asarray(reg["embedding"], float))
            if c > raw_sim:
                raw_best, raw_sim = reg, c
        matched = bool(match and sim >= threshold)
        print(f"[얼굴진단] 기준표본={self._ref_count} 활성={ref_active} | "
              f"원본최고={raw_sim:.3f}({raw_best['nickname'] if raw_best else '-'}) "
              f"보정최고={sim:.3f}({match['nickname'] if match else '-'}) "
              f"임계값={threshold} → {'매칭' if matched else '거부'} "
              f"(연속{self._stable_count})", flush=True)

    def reset_tracking(self) -> None:
        """주문이 끝나면 추적 상태를 초기화합니다."""
        self._stable_id = None
        self._stable_count = 0
        self._announced_id = None

    # ──────────────────────────────────────────
    # 등록 / 갱신
    # ──────────────────────────────────────────
    def register(self, nickname: str, embedding: np.ndarray, favorite: dict) -> int:
        """새 단골을 DB 에 등록하고 캐시를 갱신합니다."""
        rid = self.db.add_regular(nickname, embedding, favorite)
        self.reload()
        self._accumulate(embedding)                 # 새 얼굴도 기준 평균에 반영
        return rid

    def update_favorite(self, regular_id: int, favorite: dict) -> None:
        self.db.update_visit(regular_id, favorite)
        self.reload()

    def suggest_nickname(self, base: str = "단골") -> str:
        """중복되지 않는 추천 별명을 만듭니다."""
        i = 1
        while self.db.nickname_exists(f"{base}{i}"):
            i += 1
        return f"{base}{i}"
