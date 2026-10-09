"""
core/vision.py — 비전 AI 엔진 (계획서 2.1 / 2.2 / 2.3 / 4.3)
================================================
카메라 영상에서 얼굴과 손을 실시간으로 분석하는 핵심 백엔드입니다.

QThread 기반 비동기 멀티스레딩(계획서 4.3):
  · UI(화면)가 멈추지 않도록 카메라 처리는 별도 스레드에서 돌립니다.
  · 분석 결과는 Qt 시그널(signal)로 UI 에 안전하게 전달합니다.

처리 내용
  1) MediaPipe Face Mesh  → 얼굴 위치 찾기      → 연령대 분류(어린이/성인/노인) → 화면 자동 전환
  2) MediaPipe Hands      → 손 관절 21개         → 제스처(에임 커서/핀치·주먹 담기/스와이프)
  3) 히스토그램 평활화(CLAHE) 계산 — 조명 보정 원리 구현(계획서 4.2).
     인식(MediaPipe·연령 CNN)에는 학습 조건과 같은 원본 컬러 영상을 그대로 씁니다.

얼굴은 연령대 분류에만 쓰며, 사진·얼굴 특징 숫자를 저장하거나 개인을 식별하지 않습니다.

라이브러리(opencv/mediapipe)나 카메라가 없으면 자동으로 '데모 모드' 로 동작하여
시그널만 쉬게 두고, UI 의 수동 조작으로 모든 기능을 시연할 수 있습니다.
"""
from __future__ import annotations

import time
from collections import Counter, deque

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
    SWIPE_MIN_DISTANCE, SWIPE_COOLDOWN_MS, FIST_HOLD_FRAMES, AGE_INFER_EVERY,
    FINGER_EXTEND_RATIO, FINGER_FOLD_RATIO, FINGER_ANGLE_EXTEND_DEG,
    FINGER_ANGLE_FOLD_DEG, GESTURE_VOTE_WINDOW, GESTURE_VOTE_MIN, PINCH_RATIO,
    ONE_EURO_MIN_CUTOFF, ONE_EURO_BETA, ONE_EURO_DCUTOFF, AIM_USE_PALM,
)
from core.mathutils import OneEuroFilter, cosine_similarity, equalize_lighting
from core.age_model import AgeEstimator


# ──────────────────────────────────────────────
# 얼굴 위치 / 연령 추정 도우미 함수
# ──────────────────────────────────────────────
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

    인식 제스처(안정적인 '에임 + 핀치 + 드웰' 조합):
      · 손을 편하게 들기(펼친 손/검지/V)  → point / open_palm / sign_two / idle (커서 이동)
      · 핀치(엄지·검지 집기) / 주먹  → fist (가리킨 메뉴 담기)
      · 손바닥 펴서 좌/우로 휘두르기 → swipe_left / swipe_right (카테고리 넘기기)
      · 엄지척                      → sign_yes (팝업 '예' 확인. 메뉴에선 주먹과 같게 처리, 결제엔 안 씀)

    정확도 개선(플리커/떨림/오인식 억제):
      · 손가락 펴짐 판정에 히스테리시스(이중 임계값) + 관절 각도 병행
      · 손 모양을 최근 N프레임 다수결로 확정(순간 오발 제거)
      · 커서를 One-Euro 필터로 스무딩(가리키기 커서 떨림 제거)
      · 손 크기로 스와이프/핀치 임계를 정규화(카메라 거리 무관)
    """

    # 손가락별 (tip, pip, mcp) 랜드마크 번호
    _FINGERS = {8: (8, 6, 5), 12: (12, 10, 9), 16: (16, 14, 13), 20: (20, 18, 17)}

    def __init__(self):
        # 커서용 One-Euro 필터(검지 끝 / 손바닥 중심을 각각 x·y로 스무딩)
        self._tip_fx = OneEuroFilter(ONE_EURO_MIN_CUTOFF, ONE_EURO_BETA, ONE_EURO_DCUTOFF)
        self._tip_fy = OneEuroFilter(ONE_EURO_MIN_CUTOFF, ONE_EURO_BETA, ONE_EURO_DCUTOFF)
        self._palm_fx = OneEuroFilter(ONE_EURO_MIN_CUTOFF, ONE_EURO_BETA, ONE_EURO_DCUTOFF)
        self._palm_fy = OneEuroFilter(ONE_EURO_MIN_CUTOFF, ONE_EURO_BETA, ONE_EURO_DCUTOFF)
        # 손가락 펴짐 상태 캐시(히스테리시스: 경계에서 직전 상태 유지)
        self._finger_state: dict[int, bool] = {8: False, 12: False, 16: False, 20: False}
        self._thumb_state = False
        # 손 모양 다수결 투표 큐
        self._pose_votes: deque[tuple] = deque(maxlen=GESTURE_VOTE_WINDOW)
        self._last_x: float | None = None
        self._last_swipe_t = 0.0
        self._fist_frames = 0
        self._signyes_frames = 0

    @staticmethod
    def _dist(a, b) -> float:
        """두 랜드마크 사이의 평면 거리."""
        return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5

    @staticmethod
    def _joint_angle(a, b, c) -> float:
        """관절 b에서 벡터 b→a 와 b→c 사이의 각도(도). 손가락 펴짐 판정용.

        코사인 유사도 공식 (A·B)/(‖A‖‖B‖) 로 cosθ 를 구한 뒤 arccos 로 각도를 얻습니다.
        """
        v1 = np.array([a.x - b.x, a.y - b.y])
        v2 = np.array([c.x - b.x, c.y - b.y])
        if not np.any(v1) or not np.any(v2):
            return 180.0
        cosang = float(np.clip(cosine_similarity(v1, v2), -1.0, 1.0))
        return float(np.degrees(np.arccos(cosang)))

    def _finger_extended(self, lm, tip: int) -> bool:
        """손가락이 펴졌는지 판별 — 거리비 + 관절 각도 + 히스테리시스.

        · 거리비: 손목에서 손끝이 둘째마디보다 얼마나 더 먼가.
        · 각도: PIP 관절이 얼마나 펴졌는가(손이 기울어도 강건).
        · 히스테리시스: 확실할 때만 상태를 바꾸고, 경계(애매)에서는 직전 상태 유지
          → 경계에서 매 프레임 뒤집히는 '플리커'를 근본적으로 제거.
        """
        t, pip, mcp = self._FINGERS[tip]
        w = lm[0]
        ratio = self._dist(lm[t], w) / (self._dist(lm[pip], w) + 1e-9)
        angle = self._joint_angle(lm[mcp], lm[pip], lm[t])
        prev = self._finger_state[tip]
        if ratio >= FINGER_EXTEND_RATIO and angle >= FINGER_ANGLE_EXTEND_DEG:
            state = True                                   # 확실히 펴짐
        elif ratio <= FINGER_FOLD_RATIO or angle <= FINGER_ANGLE_FOLD_DEG:
            state = False                                  # 확실히 접힘
        else:
            state = prev                                   # 경계 → 직전 상태 유지
        self._finger_state[tip] = state
        return state

    def _thumb_extended(self, lm) -> bool:
        """엄지 펴짐 판별(각도 랜드마크가 불안정해 거리비 히스테리시스만 사용)."""
        w = lm[0]
        ratio = self._dist(lm[4], w) / (self._dist(lm[3], w) + 1e-9)
        if ratio >= 1.25:
            self._thumb_state = True
        elif ratio <= 1.05:
            self._thumb_state = False
        return self._thumb_state

    def classify(self, hand_landmarks) -> tuple[str, tuple[float, float]]:
        """제스처 이름과 (정규화된 커서 위치)를 돌려줍니다."""
        lm = hand_landmarks.landmark
        now = time.time() * 1000
        # 손 크기(손목0~중지뿌리9): 스와이프·핀치 임계를 카메라 거리와 무관하게 정규화.
        hand_scale = self._dist(lm[0], lm[9]) or 1e-6

        # 손가락 펴짐 상태(히스테리시스+각도)
        index = self._finger_extended(lm, 8)
        middle = self._finger_extended(lm, 12)
        ring = self._finger_extended(lm, 16)
        pinky = self._finger_extended(lm, 20)
        thumb = self._thumb_extended(lm)
        # 핀치(집기): 엄지끝~검지끝 거리를 손 크기로 정규화
        pinch = (self._dist(lm[4], lm[8]) / hand_scale) < PINCH_RATIO

        # ── 다중 프레임 다수결: 최근 N프레임 손모양이 과반일 때만 그 모양으로 확정 ──
        pattern = (index, middle, ring, pinky, thumb, pinch)
        self._pose_votes.append(pattern)
        top, cnt = Counter(self._pose_votes).most_common(1)[0]
        if cnt >= GESTURE_VOTE_MIN:
            index, middle, ring, pinky, thumb, pinch = top
        n_main = sum([index, middle, ring, pinky])

        # 커서 좌표(One-Euro 스무딩): 검지 끝 / 손바닥 중심
        tip_x = self._tip_fx.filter(lm[8].x, now)
        tip_y = self._tip_fy.filter(lm[8].y, now)
        palm_x = self._palm_fx.filter((lm[0].x + lm[9].x) / 2, now)
        palm_y = self._palm_fy.filter((lm[0].y + lm[9].y) / 2, now)

        # 0) 핀치(집기) → 담기. 주먹보다 안정적이라 먼저 판정.
        if pinch:
            self._last_x = None
            self._signyes_frames = 0
            self._fist_frames += 1
            if self._fist_frames >= FIST_HOLD_FRAMES:
                self._fist_frames = 0
                return "fist", (tip_x, tip_y)
            return "fist_hold", (tip_x, tip_y)

        # 1) 검지만 펴짐 → 포인팅(커서 이동). 가리키기 우선.
        if index and not middle and not ring and not pinky:
            self._fist_frames = 0
            self._last_x = None
            # 에임(커서)은 손바닥 중심이 더 안정적. 정밀 포인팅이 필요하면 손끝 사용.
            if AIM_USE_PALM:
                return "point", (palm_x, palm_y)
            return "point", (tip_x, tip_y)

        # 2) 네 손가락이 접힘(닫힌 손) → 담기(fist). 엄지가 또렷하면 확인(sign_yes).
        #    fist/sign_yes 모두 몇 프레임 '유지'돼야 확정(엄지 깜빡임 무시).
        if n_main == 0:
            self._last_x = None
            if thumb:
                self._fist_frames = 0
                self._signyes_frames += 1
                if self._signyes_frames >= FIST_HOLD_FRAMES:
                    self._signyes_frames = 0
                    return "sign_yes", (palm_x, palm_y)
                return "sign_hold", (palm_x, palm_y)
            self._signyes_frames = 0
            self._fist_frames += 1
            if self._fist_frames >= FIST_HOLD_FRAMES:
                self._fist_frames = 0
                return "fist", (palm_x, palm_y)
            return "fist_hold", (palm_x, palm_y)
        self._fist_frames = 0
        self._signyes_frames = 0

        # 3) 검지+중지만 → V(둘)
        if index and middle and not ring and not pinky:
            return "sign_two", (palm_x, palm_y)

        # 4) 손가락 다수 펼침 → 좌우 스와이프 / 손바닥
        if n_main >= 3:
            # 스와이프 최소 이동량을 손 크기로 정규화(멀든 가깝든 일관).
            min_dist = SWIPE_MIN_DISTANCE * (hand_scale / 0.18)
            if self._last_x is not None and (now - self._last_swipe_t) > SWIPE_COOLDOWN_MS:
                dx = palm_x - self._last_x
                if dx > min_dist:
                    self._last_swipe_t = now
                    self._last_x = palm_x
                    return "swipe_right", (palm_x, palm_y)
                if dx < -min_dist:
                    self._last_swipe_t = now
                    self._last_x = palm_x
                    return "swipe_left", (palm_x, palm_y)
            self._last_x = palm_x
            return "open_palm", (palm_x, palm_y)

        self._last_x = palm_x
        return "idle", (palm_x, palm_y)


# ──────────────────────────────────────────────
# 비전 처리 스레드 (QThread)
# ──────────────────────────────────────────────
if _QT:
    class VisionThread(QThread):
        """카메라를 읽어 얼굴/손을 분석하고 결과를 시그널로 보내는 스레드."""

        # UI 로 보내는 신호들
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
