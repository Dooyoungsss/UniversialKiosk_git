"""
core/vision.py — 비전 AI 엔진 (계획서 2.1 / 2.2 / 2.3 / 4.3)
================================================
카메라 영상에서 얼굴과 손을 실시간으로 분석하는 핵심 백엔드입니다.

QThread 기반 비동기 멀티스레딩(계획서 4.3):
  · UI(화면)가 멈추지 않도록 카메라 처리는 별도 스레드에서 돌립니다.
  · 분석 결과는 Qt 시그널(signal)로 UI 에 안전하게 전달합니다.

처리 내용
  1) MediaPipe Face Mesh  → 안면 랜드마크 468개  → 연령대 추정 + 얼굴 임베딩
  2) MediaPipe Hands      → 손 관절 21개         → 제스처(스와이프/주먹/펼침/수어)
  3) 히스토그램 평활화로 조명/역광 보정(계획서 4.2)

라이브러리(opencv/mediapipe)나 카메라가 없으면 자동으로 '데모 모드' 로 동작하여
시그널만 쉬게 두고, UI 의 수동 조작으로 모든 기능을 시연할 수 있습니다.
"""
from __future__ import annotations

import time
import numpy as np

try:
    from PyQt6.QtCore import QThread, pyqtSignal
    _QT = True
except Exception:                      # PyQt6 미설치 환경 보호
    _QT = False
    class QThread:                     # type: ignore
        pass
    def pyqtSignal(*a, **k):           # type: ignore
        return None

from config import (
    CAMERA_INDEX, FRAME_WIDTH, FRAME_HEIGHT, FACE_MAX_NUM, HAND_MAX_NUM,
    MOVING_AVERAGE_WINDOW, SWIPE_MIN_DISTANCE, SWIPE_COOLDOWN_MS, FIST_HOLD_FRAMES,
    AGE_INFER_EVERY,
)
from core.mathutils import MovingAverageFilter, normalize_vector, equalize_lighting
from core.age_model import AgeEstimator


# ──────────────────────────────────────────────
# 얼굴 임베딩 / 연령 추정 도우미 함수
# ──────────────────────────────────────────────
def landmarks_to_embedding(landmarks) -> np.ndarray:
    """468개 얼굴 랜드마크를 '코를 기준으로 정규화한 숫자 배열'로 바꿉니다.

    개인정보 보호: 사진이 아니라 좌표의 상대적 모양만 남깁니다(계획서 2.2).
    얼굴 위치·크기가 달라져도 같은 사람은 비슷한 벡터가 나오도록 정규화합니다.
    """
    pts = np.array([[lm.x, lm.y, lm.z] for lm in landmarks], dtype=np.float64)
    nose = pts[1]                       # 코끝(1번)을 원점으로
    pts = pts - nose
    scale = np.linalg.norm(pts, axis=1).max()
    if scale > 0:
        pts = pts / scale               # 얼굴 크기에 상관없이 비교 가능하도록 정규화
    # 식별에 중요한 주요 랜드마크만 추려서 가벼운 임베딩 생성
    key_idx = [33, 133, 362, 263, 1, 61, 291, 199, 168, 6, 197, 195,
               5, 4, 98, 327, 0, 17, 13, 14, 78, 308, 234, 454]
    emb = pts[key_idx].flatten()
    return normalize_vector(emb)


def landmarks_to_bbox(landmarks, frame_w: int, frame_h: int):
    """얼굴 랜드마크(정규화 0~1 좌표)에서 픽셀 단위 경계상자를 만듭니다.

    연령 분류 모델에 넣을 '얼굴만 잘라낸 이미지'의 위치를 잡는 데 씁니다.
    """
    xs = [lm.x for lm in landmarks]
    ys = [lm.y for lm in landmarks]
    x1 = int(min(xs) * frame_w); x2 = int(max(xs) * frame_w)
    y1 = int(min(ys) * frame_h); y2 = int(max(ys) * frame_h)
    return x1, y1, x2, y2


def estimate_age_group(landmarks, frame_h: int) -> str:
    """랜드마크 기하 비율로 연령대를 대략 추정합니다(휴리스틱).

    실제 정밀 연령 모델 대신, 얼굴 비율 휴리스틱으로 'child/adult/senior' 를 추정합니다.
    어린이는 얼굴 대비 눈 간격 비율이 큰 편이라는 특징을 활용합니다.
    (대회 시연에서는 UI 의 모드 버튼으로 확실히 전환 시연도 가능)
    """
    pts = np.array([[lm.x, lm.y] for lm in landmarks], dtype=np.float64)
    # 두 눈 사이 거리 / 얼굴 세로 길이 비율
    left_eye, right_eye = pts[33], pts[263]
    chin, forehead = pts[152], pts[10]
    eye_dist = np.linalg.norm(left_eye - right_eye)
    face_h = np.linalg.norm(chin - forehead)
    if face_h <= 0:
        return "adult"
    ratio = eye_dist / face_h
    if ratio > 0.62:
        return "child"
    if ratio < 0.50:
        return "senior"
    return "adult"


# ──────────────────────────────────────────────
# 제스처 인식기
# ──────────────────────────────────────────────
class GestureRecognizer:
    """손 관절 21개 좌표로 제스처를 판별하는 클래스.

    인식 제스처(계획서 2.3):
      · 손바닥 펼쳐 좌/우로 휘두르기 → swipe_left / swipe_right (카테고리 넘기기)
      · 주먹 쥐기                    → fist (장바구니에 담기)
      · 검지로 가리키기              → point (커서 이동, 이동평균 필터 적용)
      · 간단 수어(엄지척/V/하이파이브) → sign_yes / sign_two / sign_hello
    """

    def __init__(self):
        self.filter = MovingAverageFilter(MOVING_AVERAGE_WINDOW)
        self._last_x: float | None = None
        self._last_swipe_t = 0.0
        self._fist_frames = 0
        self._signyes_frames = 0

    @staticmethod
    def _dist(a, b) -> float:
        """두 랜드마크 사이의 평면 거리."""
        return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5

    def _finger_extended(self, lm, tip, pip, k: float = 1.05) -> bool:
        """손가락이 펴졌는지 판별.

        손목(0번)에서 '손끝(tip)'이 '둘째마디(pip)'보다 멀리 있으면 펴진 것으로 본다.
        단순 y 비교와 달리 손이 기울거나 옆으로 누워도 안정적으로 동작한다(강건성).
        """
        w = lm[0]
        return self._dist(lm[tip], w) > self._dist(lm[pip], w) * k

    def classify(self, hand_landmarks) -> tuple[str, tuple[float, float]]:
        """제스처 이름과 (정규화된 손 위치)를 돌려줍니다."""
        lm = hand_landmarks.landmark
        # 손가락 펴짐 상태(손목 기준 거리) [엄지, 검지, 중지, 약지, 새끼]
        index = self._finger_extended(lm, 8, 6)
        middle = self._finger_extended(lm, 12, 10)
        ring = self._finger_extended(lm, 16, 14)
        pinky = self._finger_extended(lm, 20, 18)
        thumb = self._finger_extended(lm, 4, 3, k=1.2)   # 엄지는 더 또렷할 때만
        n_main = sum([index, middle, ring, pinky])       # 엄지 제외 네 손가락

        # 손바닥 중심(0번 손목 ~ 9번 중지뿌리 평균)을 커서 위치로 사용
        cx = (lm[0].x + lm[9].x) / 2
        cy = (lm[0].y + lm[9].y) / 2
        sx, sy = self.filter.update(cx, cy)   # 이동평균 필터로 떨림 제거

        now = time.time() * 1000

        # 1) 검지만 펴짐 → 포인팅(커서 이동). 가장 먼저 판정(가리키기 우선).
        if index and not middle and not ring and not pinky:
            self._fist_frames = 0
            self._last_x = None
            return "point", (lm[8].x, lm[8].y)

        # 2) 네 손가락이 접힘(닫힌 손) → 담기(fist). 엄지가 또렷이 펴지면 확인(sign_yes).
        #    핵심: 엄지가 어떻든 손이 닫히면 'fist' 로 본다(주먹 인식 누락 방지).
        #    오발 방지: fist/sign_yes 모두 몇 프레임 '유지'돼야 확정한다(엄지 깜빡임 무시).
        if n_main == 0:
            self._last_x = None
            if thumb:
                self._fist_frames = 0
                self._signyes_frames += 1
                if self._signyes_frames >= FIST_HOLD_FRAMES:
                    self._signyes_frames = 0
                    return "sign_yes", (sx, sy)      # 엄지척 = 네/확인(유지 확정)
                return "sign_hold", (sx, sy)
            self._signyes_frames = 0
            self._fist_frames += 1
            if self._fist_frames >= FIST_HOLD_FRAMES:
                self._fist_frames = 0
                return "fist", (sx, sy)
            return "fist_hold", (sx, sy)
        self._fist_frames = 0
        self._signyes_frames = 0

        # 3) 검지+중지만 → V(둘)
        if index and middle and not ring and not pinky:
            return "sign_two", (sx, sy)

        # 4) 손가락 다수 펼침 → 좌우 스와이프 / 손바닥
        if n_main >= 3:
            if self._last_x is not None and (now - self._last_swipe_t) > SWIPE_COOLDOWN_MS:
                dx = sx - self._last_x
                if dx > SWIPE_MIN_DISTANCE:
                    self._last_swipe_t = now
                    self._last_x = sx
                    return "swipe_right", (sx, sy)
                if dx < -SWIPE_MIN_DISTANCE:
                    self._last_swipe_t = now
                    self._last_x = sx
                    return "swipe_left", (sx, sy)
            self._last_x = sx
            return "open_palm", (sx, sy)

        self._last_x = sx
        return "idle", (sx, sy)


# ──────────────────────────────────────────────
# 비전 처리 스레드 (QThread)
# ──────────────────────────────────────────────
if _QT:
    class VisionThread(QThread):
        """카메라를 읽어 얼굴/손을 분석하고 결과를 시그널로 보내는 스레드."""

        # UI 로 보내는 신호들
        face_embedding = pyqtSignal(object)     # np.ndarray (얼굴 임베딩 벡터)
        age_group = pyqtSignal(str)             # "child"/"adult"/"senior"
        face_present = pyqtSignal(bool)         # 얼굴 감지 여부
        gesture = pyqtSignal(str, float, float)  # 제스처 이름, 커서 x, 커서 y
        frame_ready = pyqtSignal(object)        # 미리보기용 영상(numpy BGR)
        status = pyqtSignal(str)                # 상태 메시지

        def __init__(self, parent=None):
            super().__init__(parent)
            self._running = False
            self.gesture_recognizer = GestureRecognizer()
            self.age_estimator = None        # 카메라 시작 시 로드(어린이/성인/노인)
            self.available = False

        def run(self) -> None:
            self._running = True
            # ── 라이브러리 로드 ──
            # MediaPipe 버전마다 solutions API 위치가 다르고, 일부 빌드에는
            # 아예 빠져 있기도 합니다. 여러 경로를 차례로 시도하고, 모두 실패하면
            # 깔끔하게 데모 모드로 넘어가 앱이 절대 죽지 않도록 합니다.
            try:
                import cv2
            except Exception:
                self.status.emit("vision_demo_no_opencv")
                return

            mp_face_mesh = mp_hands_mod = None
            try:
                import mediapipe as mp
                mp_face_mesh = mp.solutions.face_mesh
                mp_hands_mod = mp.solutions.hands
            except Exception:
                try:
                    from mediapipe.python.solutions import face_mesh as mp_face_mesh
                    from mediapipe.python.solutions import hands as mp_hands_mod
                except Exception:
                    self.status.emit("vision_demo_no_mediapipe")
                    return

            cap = cv2.VideoCapture(CAMERA_INDEX)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
            if not cap.isOpened():
                self.status.emit("vision_demo_no_camera")
                return

            # 모델 초기화도 실패할 수 있으므로 보호합니다.
            try:
                mp_face = mp_face_mesh.FaceMesh(
                    max_num_faces=FACE_MAX_NUM, refine_landmarks=True,
                    min_detection_confidence=0.5, min_tracking_confidence=0.5)
                mp_hands = mp_hands_mod.Hands(
                    max_num_hands=HAND_MAX_NUM,
                    min_detection_confidence=0.6, min_tracking_confidence=0.5)
            except Exception:
                cap.release()
                self.status.emit("vision_demo_init_fail")
                return

            self.available = True
            # 연령 분류 모델 로드(없으면 available=False → 기하 휴리스틱으로 대체)
            self.age_estimator = AgeEstimator()
            self.status.emit("vision_running")

            last_face_state = False
            frame_idx = 0
            try:
                while self._running:
                    ok, frame = cap.read()
                    if not ok:
                        continue
                    frame = cv2.flip(frame, 1)        # 거울처럼 좌우 반전
                    frame_idx += 1

                    # 4.2 조명 보정: 그레이 변환 후 히스토그램 평활화
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    equalize_lighting(gray)           # 인식 신뢰성 보강(데모 시 효과 설명용)

                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                    # ── 얼굴 분석 ──
                    face_res = mp_face.process(rgb)
                    if face_res.multi_face_landmarks:
                        lms = face_res.multi_face_landmarks[0].landmark
                        if not last_face_state:
                            self.face_present.emit(True)
                            last_face_state = True
                        emb = landmarks_to_embedding(lms)
                        self.face_embedding.emit(emb)
                        # 연령(어린이/성인/노인): 학습된 CNN 우선, 없으면 기하 휴리스틱.
                        # 추론이 무거우므로 N프레임마다 1회만 실행합니다.
                        group = None
                        if (self.age_estimator.available
                                and frame_idx % AGE_INFER_EVERY == 0):
                            fh, fw = frame.shape[:2]
                            bbox = landmarks_to_bbox(lms, fw, fh)
                            group, _ = self.age_estimator.predict_group(frame, bbox)
                        elif not self.age_estimator.available:
                            group = estimate_age_group(lms, FRAME_HEIGHT)
                        if group is not None:
                            self.age_group.emit(group)
                    else:
                        if last_face_state:
                            self.face_present.emit(False)
                            last_face_state = False

                    # ── 손 분석 ──
                    hand_res = mp_hands.process(rgb)
                    if hand_res.multi_hand_landmarks:
                        g, (gx, gy) = self.gesture_recognizer.classify(
                            hand_res.multi_hand_landmarks[0])
                        self.gesture.emit(g, float(gx), float(gy))
                        # 미리보기에 손 위치 표시
                        cv2.circle(frame, (int(gx * frame.shape[1]),
                                           int(gy * frame.shape[0])), 12, (0, 255, 0), -1)

                    self.frame_ready.emit(frame)
                    self.msleep(15)                  # 약 60fps 상한
            except Exception:
                self.status.emit("vision_interrupted")
            finally:
                cap.release()
                try:
                    mp_face.close()
                    mp_hands.close()
                except Exception:
                    pass
                self.status.emit("vision_stopped")

        def stop(self) -> None:
            self._running = False
            self.wait(1500)
else:
    class VisionThread:                # PyQt6 없을 때의 더미(임포트 오류 방지)
        available = False
        def start(self): ...
        def stop(self): ...
