"""
core/age_model.py — 연령대 분류(어린이 / 성인 / 노인)
================================================
카메라 속 얼굴을 학습된 CNN(OpenCV DNN, Caffe)으로 3그룹으로 분류합니다.

왜 이 방식인가:
  · MediaPipe 랜드마크의 '기하 비율' 휴리스틱은 거리·각도에 너무 민감해
    실제 카메라에서는 아이를 노인으로 오판하는 등 신뢰할 수 없었습니다.
  · 그래서 얼굴 이미지를 직접 보고 나이를 추정하도록 학습된 모델을 씁니다.

모델 파일(data/models/):
  · age_deploy.prototxt  (망 구조)
  · age_net.caffemodel   (가중치, Levi-Hassner / Adience 학습)
파일이 없거나 로드에 실패하면 available=False 가 되고, 호출부는 기존
기하 휴리스틱으로 자동 대체합니다(앱이 절대 죽지 않도록).
"""
from __future__ import annotations

import numpy as np

import config

# 모델이 출력하는 8개 연령 구간(학습 시 정의된 순서, 절대 바꾸지 말 것)
AGE_BUCKETS = ["(0-2)", "(4-6)", "(8-12)", "(15-20)",
               "(25-32)", "(38-43)", "(48-53)", "(60-100)"]
# 학습 때 사용한 BGR 평균값(입력 정규화에 그대로 사용)
MODEL_MEAN = (78.4263377603, 87.7689143744, 114.895847746)


def bucket_to_group(idx: int) -> str:
    """8개 구간 인덱스를 어린이/성인/노인 3그룹으로 묶습니다.

      · 0~12세  → child  (어린이: 큰 글씨·쉬운 화면)
      · 15~43세 → adult  (성인: 표준 화면)
      · 48세~   → senior (노인: 큰 글씨·고대비, 접근성 우선)
    """
    if idx <= 2:
        return "child"
    if idx <= 5:
        return "adult"
    return "senior"


class AgeEstimator:
    """얼굴 crop 한 장을 받아 child/adult/senior 를 돌려주는 추정기."""

    def __init__(self) -> None:
        self.net = None
        self.available = False
        self._load()

    def _load(self) -> None:
        try:
            import cv2
            proto = config.DATA_DIR / "models" / "age_deploy.prototxt"
            model = config.DATA_DIR / "models" / "age_net.caffemodel"
            if not (proto.exists() and model.exists()):
                return
            self.net = cv2.dnn.readNetFromCaffe(str(proto), str(model))
            self.available = True
        except Exception:
            self.net = None
            self.available = False

    def predict_group(self, frame_bgr, bbox) -> tuple[str | None, float]:
        """얼굴 영역(bbox=(x1,y1,x2,y2) 픽셀)을 보고 (그룹, 신뢰도)를 돌려줍니다.

        모델이 없거나 얼굴이 너무 작으면 (None, 0.0) 을 돌려주어
        호출부가 휴리스틱으로 대체하도록 합니다.
        """
        if not self.available:
            return None, 0.0
        try:
            import cv2
            h, w = frame_bgr.shape[:2]
            x1, y1, x2, y2 = bbox
            # 얼굴 주변에 약간의 여백을 둬야(턱·이마 포함) 추정이 안정적입니다.
            mx = int((x2 - x1) * 0.20)
            my = int((y2 - y1) * 0.20)
            x1 = max(0, x1 - mx); y1 = max(0, y1 - my)
            x2 = min(w, x2 + mx); y2 = min(h, y2 + my)
            if x2 - x1 < 20 or y2 - y1 < 20:
                return None, 0.0
            face = frame_bgr[y1:y2, x1:x2]
            blob = cv2.dnn.blobFromImage(
                face, 1.0, (227, 227), MODEL_MEAN, swapRB=False)
            self.net.setInput(blob)
            preds = self.net.forward().flatten()
            idx = int(np.argmax(preds))
            return bucket_to_group(idx), float(preds[idx])
        except Exception:
            return None, 0.0
