"""
core/mathutils.py — STEAM 수학·과학 원리 구현부
================================================
계획서 4.1(수학)·4.2(과학)에서 설명한 수식을 실제 코드로 구현한 곳입니다.
대회 심사 때 "이 함수가 계획서의 그 공식입니다" 라고 보여줄 수 있는 핵심 파일입니다.

  · 유클리디안 거리 (Euclidean Distance)   →  euclidean_distance()
  · 코사인 유사도     (Cosine Similarity)   →  cosine_similarity()
  · 이동 평균 필터    (Moving Average)      →  MovingAverageFilter
  · 히스토그램 평활화 (Histogram Equalize)  →  equalize_lighting()
"""
from __future__ import annotations

from collections import deque
from typing import Sequence

import numpy as np


# ──────────────────────────────────────────────
# 4.1 유클리디안 거리:  d = √Σ(xᵢ − yᵢ)²
# ──────────────────────────────────────────────
def euclidean_distance(a: Sequence[float], b: Sequence[float]) -> float:
    """두 점(또는 벡터) 사이의 직선 거리를 계산합니다.

    계획서 공식:  d = √Σ(xᵢ − yᵢ)²
    얼굴 랜드마크 좌표 사이 거리를 잴 때 사용합니다(예: 눈 크기 변화율).
    """
    va = np.asarray(a, dtype=np.float64)
    vb = np.asarray(b, dtype=np.float64)
    return float(np.sqrt(np.sum((va - vb) ** 2)))


# ──────────────────────────────────────────────
# 4.1 코사인 유사도:  similarity = (A·B) / (‖A‖‖B‖)
# ──────────────────────────────────────────────
def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """두 벡터가 이루는 각도로 '얼마나 닮았는지'를 -1~1 사이 값으로 계산합니다.

    계획서 공식:  Similarity = (A · B) / (‖A‖ · ‖B‖)
    단골 DB 의 얼굴 임베딩과 현재 얼굴 임베딩이 같은 사람인지 판별할 때 사용합니다.
    1 에 가까울수록 같은 사람입니다.
    """
    va = np.asarray(a, dtype=np.float64)
    vb = np.asarray(b, dtype=np.float64)
    norm_a = np.linalg.norm(va)
    norm_b = np.linalg.norm(vb)
    if norm_a == 0 or norm_b == 0:        # 0 벡터 예외 처리(0 으로 나누기 방지)
        return 0.0
    return float(np.dot(va, vb) / (norm_a * norm_b))


def normalize_vector(v: Sequence[float]) -> np.ndarray:
    """벡터의 크기를 1 로 맞춥니다(정규화). 비교를 안정적으로 만들어 줍니다."""
    arr = np.asarray(v, dtype=np.float64)
    norm = np.linalg.norm(arr)
    if norm == 0:
        return arr
    return arr / norm


# ──────────────────────────────────────────────
# 4.2 이동 평균 필터(Moving Average Filter) — 손떨림 잡음 제거
# ──────────────────────────────────────────────
class MovingAverageFilter:
    """최근 N개의 좌표를 평균 내어 손가락 떨림(잡음)을 부드럽게 만드는 필터.

    계획서 4.2: "이동 평균 필터를 활용하여 부드러운 커서 제어 신호로 변환"
    제스처 인식에서 손 좌표가 미세하게 떨릴 때 이 필터를 통과시키면
    커서가 안정적으로 움직입니다.
    """

    def __init__(self, window: int = 5):
        self.window = max(1, window)
        self._buf_x: deque[float] = deque(maxlen=self.window)
        self._buf_y: deque[float] = deque(maxlen=self.window)

    def update(self, x: float, y: float) -> tuple[float, float]:
        """새 좌표를 넣고, 평활화된 좌표를 돌려줍니다."""
        self._buf_x.append(x)
        self._buf_y.append(y)
        return (sum(self._buf_x) / len(self._buf_x),
                sum(self._buf_y) / len(self._buf_y))

    def reset(self) -> None:
        self._buf_x.clear()
        self._buf_y.clear()


# ──────────────────────────────────────────────
# 4.2 광학 환경 분석 — 히스토그램 평활화(역광/조도 보정)
# ──────────────────────────────────────────────
def equalize_lighting(gray_image: np.ndarray) -> np.ndarray:
    """밝기가 한쪽으로 치우친 영상을 골고루 펴주어 인식률을 높입니다.

    계획서 4.2: "영상 이진화 및 히스토그램 평활화 알고리즘을 구현하여
    비전 인식률의 신뢰성을 실험적으로 확보".
    OpenCV 의 CLAHE(적응형 히스토그램 평활화)를 사용합니다.
    cv2 가 없으면 원본을 그대로 돌려줍니다(견고성).
    """
    try:
        import cv2
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(gray_image)
    except Exception:
        return gray_image
