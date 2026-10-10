"""
core/i18n.py — 다국어 텍스트 (계획서 2.4: 영어 모드 실시간 전환)
================================================
UI 에 표시되는 모든 글자를 한국어/영어/중국어로 정리해 둔 사전입니다.
LANG 변수만 바꾸면 화면 전체 언어가 즉시 바뀝니다.

· 지원 언어: 한국어("ko") · 영어("en") · 중국어 간체("zh")
· 세 사전은 항상 같은 키를 가져야 합니다(test_i18n_key_parity).
"""
from __future__ import annotations

# 언어 전환 순서(🌐 버튼을 누르면 이 순서로 순환)
LANG_ORDER = ["ko", "en", "zh"]

# 🌐 버튼에 표시할 '다음 언어' 이름
LANG_NEXT_LABEL = {
    "ko": "🌐 English",
    "en": "🌐 中文",
    "zh": "🌐 한국어",
}

TEXTS = {
    "ko": {
        # ── 환영 / 기본 ──
        "store_name": "노프라블럼 버거",
        "welcome_title": "어서 오세요!",
        "welcome_sub": "화면을 터치하거나, 손동작 · 음성으로 주문하세요",
        "start_order": "주문 시작하기",
        "cart": "장바구니",
        "cart_empty": "담은 메뉴가 없어요",
        "total": "합계",
        "checkout": "결제하기",
        "clear": "전체 비우기",
        "add": "담기",
        "set_toggle": "세트로",
        "single": "단품",
        "voice_order": "음성으로 주문",
        "voice_hint": "예) 불고기버거 세트 하나, 콜라는 라지로 바꿔주세요",
        "listening": "듣고 있어요...",
        "silver_mode": "큰 화면 모드",
        "child_mode": "어린이 모드",
        "standard_mode": "일반 모드",
        "contrast_mode": "고대비 모드",
        "thank_you": "주문해 주셔서 감사합니다!",
        "order_number": "주문번호",
        "best_menu": "인기 메뉴",
        "won": "원",
        "qty": "수량",
        "gesture_on": "손동작 켜짐",
        "voice_on": "음성안내 켜짐",
        "next": "다음",
        "prev": "이전",
        "back": "뒤로",
        "category_pick": "메뉴를 골라보세요",
        "added_toast": "담았어요",
        # ── 시연 도구막대 ──
        "demo_tools": "시연 도구:",
        "demo_grab": "담기",
        # ── 상태바 / 비전 ──
        "vision_preparing": "📷 비전 AI 준비 중…",
        "vision_demo": "📷 데모 모드 (시연 도구 사용)",
        "vision_running": "📷 비전 AI 작동 중 (얼굴/손 인식)",
        "vision_stopped": "📷 비전 AI 종료",
        "vision_interrupted": "📷 비전 처리 중단(데모 모드 전환)",
        "vision_demo_no_opencv": "📷 데모 모드 (OpenCV 없음)",
        "vision_demo_no_mediapipe": "📷 데모 모드 (MediaPipe 비전 API 없음)",
        "vision_demo_no_camera": "📷 데모 모드 (카메라를 찾을 수 없음)",
        "vision_demo_init_fail": "📷 데모 모드 (비전 모델 초기화 실패)",
        # ── 손동작 ──
        "gesture_tooltip": "손동작 제어 켜기/끄기",
        "gesture_off": "꺼짐",
        "gesture_on_toast": "✋ 손동작 제어 켜짐",
        "gesture_off_toast": "🚫 손동작 꺼짐 (화면 터치로 주문하세요)",
        "point_then_fist": "👉 누르고 싶은 메뉴나 버튼 위에 커서를 올린 뒤 🤏 집게 손으로 집어 주세요",
        "nothing_to_scroll": "목록이 한 화면에 다 보여서 넘길 내용이 없어요",
        # ── 고대비(저시력자) ──
        "contrast_tooltip": "눈이 불편한 분을 위한 고대비 화면 켜기/끄기",
        # ── 세로 화면(아래쪽 접근성 버튼 · 첫 화면 안내) ──
        "sound_btn": "소리 안내",
        "gesture_btn": "손동작",
        "welcome_hint": ("✋ 카메라에 손바닥을 보여 주면 손 커서가 나타나요. 버튼 위에서 🤏 집게 손"
                         "(엄지·검지 맞대기)을 하거나 잠시 멈추면 눌려요."),
        # ── 모드 음성 안내(TTS) ──
        "mode_silver_say": "큰 글씨 실버 모드로 바꿨어요",
        "mode_child_say": "어린이 모드로 바꿨어요",
        "mode_contrast_say": "고대비 모드로 바꿨어요",
        "mode_standard_say": "일반 모드입니다",
        # ── 담기 음성 안내 ──
        "said_added": "담았어요",
        "said_set_added": "세트 담았어요",
        # ── 음성 주문 결과 ──
        "engine_smart": "스마트 분석",
        "voice_added": "{n}개 담았어요",
        "not_understood": "메뉴를 못 알아들었어요",
        "set_word": "세트",
        "voice_item_tts": "{name} {qty}개",
        "voice_result_tts": "{items} 담았어요. 지금 합계는 {total}원입니다.",
        "cleared_tts": "장바구니를 모두 비웠어요.",
        # ── 음성 주문 창(voice_dialog) ──
        "voice_title": "음성 주문",
        "voice_natural": "자연어로 주문하세요",
        "examples_label": "예시:",
        "speak": "말하기",
        "mic_na": "마이크 미설치",
        "mic_hint": "마이크 기능: pip install SpeechRecognition PyAudio 후 사용 가능",
        "cancel": "취소",
        "analyze": "주문 분석",
        "listening_now": "듣는 중…",
        "speak_again": "다시 말하기",
        "heard": "✅ 인식됨: ",
        "calibrating": "🤫 주변 소음 측정 중…",
        "speak_now": "🎙 말씀하세요! 듣고 있어요…",
        "recognizing": "🧠 인식하는 중…",
        "no_speech": "들리지 않았어요. 다시 시도해 주세요.",
        "cannot_understand": "알아듣지 못했어요.",
        "cannot_understand_clear": "알아듣지 못했어요. 또박또박 말해 주세요.",
        "internet_required": "인터넷이 필요해요. 직접 입력하거나 예시를 눌러주세요.",
        "mic_lib_missing": "음성 라이브러리 없음",
        "error_label": "오류",
        "voice_gesture_hint": ("🤏 집게 손으로 주문 확인  ·  👈👉 스와이프로 예시 전환\n"
                               "👆 버튼 위에 손을 잠시 멈추면 자동으로 눌려요"),
        # ── 시작 접근성 안내(시각장애인·저시력자) ──
        "a11y_ask_title": "음성 도움 안내",
        "a11y_ask": ("눈이 불편하시거나 화면 글씨가 잘 안 보이시나요?\n\n"
                     "'네'라고 말씀하시거나 아래 '네' 버튼을 누르시면 "
                     "화면을 선명하게(고대비) 바꾸고 음성으로 주문을 도와드립니다."),
        "a11y_ask_tts": ("안녕하세요. 눈이 불편하시거나 화면이 잘 안 보이시나요? "
                         "그렇다면 네 라고 말씀하시거나 화면의 네 버튼을 눌러 주세요. "
                         "음성으로 주문을 도와드리겠습니다."),
        "a11y_yes": "네, 음성으로 주문할게요",
        "a11y_no": "아니요, 화면으로 주문할게요",
        "a11y_not_heard_tts": ("잘 듣지 못했어요. 화면의 큰 네 버튼을 누르시거나, "
                               "엄지와 검지 끝을 맞대어 집어 주세요."),
        # ── 음성 주문 안내(TTS) ──
        "voice_guide_tts": ("음성 주문을 시작합니다. "
                            "마이크가 켜지면 드시고 싶은 메뉴를 말씀해 주세요."),
        "voice_listen_tts": "마이크를 켰습니다. 지금 주문을 말씀해 주세요.",
        "voice_next_tts": "더 주문하시려면 말씀해 주시고, 결제하시려면 결제라고 말씀해 주세요.",
        "voice_retry_hint_tts": ("잘 듣지 못했어요. 마이크 버튼을 누르시거나 집게 손으로 눌러서 "
                                 "다시 말씀해 주세요."),
        "voice_heard_tts": ("이렇게 들었습니다. {text}. "
                            "주문하시려면 주문 분석 버튼을 누르거나 엄지와 검지 끝을 맞대어 집어 주세요."),
    },
    "en": {
        # ── 환영 / 기본 ──
        "store_name": "No Problem Burger",
        "welcome_title": "Welcome!",
        "welcome_sub": "Touch the screen, or order by gesture & voice",
        "start_order": "Start Order",
        "cart": "Cart",
        "cart_empty": "Your cart is empty",
        "total": "Total",
        "checkout": "Checkout",
        "clear": "Clear all",
        "add": "Add",
        "set_toggle": "Make Set",
        "single": "Single",
        "voice_order": "Order by Voice",
        "voice_hint": "e.g. One Bulgogi burger set, change cola to large",
        "listening": "Listening...",
        "silver_mode": "Large Screen",
        "child_mode": "Kids Mode",
        "standard_mode": "Standard",
        "contrast_mode": "High Contrast",
        "thank_you": "Thank you for your order!",
        "order_number": "Order No.",
        "best_menu": "Best Menu",
        "won": " KRW",
        "qty": "Qty",
        "gesture_on": "Gesture ON",
        "voice_on": "Voice ON",
        "next": "Next",
        "prev": "Prev",
        "back": "Back",
        "category_pick": "Pick your menu",
        "added_toast": "Added",
        # ── 시연 도구막대 ──
        "demo_tools": "Demo tools:",
        "demo_grab": "Grab",
        # ── 상태바 / 비전 ──
        "vision_preparing": "📷 Vision AI starting…",
        "vision_demo": "📷 Demo mode (use demo tools)",
        "vision_running": "📷 Vision AI running (face/hand)",
        "vision_stopped": "📷 Vision AI stopped",
        "vision_interrupted": "📷 Vision stopped (demo mode)",
        "vision_demo_no_opencv": "📷 Demo mode (OpenCV missing)",
        "vision_demo_no_mediapipe": "📷 Demo mode (MediaPipe API missing)",
        "vision_demo_no_camera": "📷 Demo mode (no camera found)",
        "vision_demo_init_fail": "📷 Demo mode (vision init failed)",
        # ── 손동작 ──
        "gesture_tooltip": "Toggle gesture control",
        "gesture_off": "OFF",
        "gesture_on_toast": "✋ Gesture control ON",
        "gesture_off_toast": "🚫 Gesture OFF (use touch)",
        "point_then_fist": "👉 Move the cursor onto a menu or button, then pinch 🤏",
        "nothing_to_scroll": "Everything already fits on the screen",
        # ── 고대비(저시력자) ──
        "contrast_tooltip": "Toggle high-contrast screen for low vision",
        # ── Portrait screen (bottom accessibility bar · welcome hint) ──
        "sound_btn": "Sound",
        "gesture_btn": "Gestures",
        "welcome_hint": ("✋ Show your palm to the camera to get a hand cursor. Pinch 🤏 (thumb to index) "
                         "or hold still on a button to press it."),
        # ── 모드 음성 안내(TTS) ──
        "mode_silver_say": "Switched to large-text silver mode",
        "mode_child_say": "Switched to kids mode",
        "mode_contrast_say": "Switched to high contrast mode",
        "mode_standard_say": "Standard mode",
        # ── 담기 음성 안내 ──
        "said_added": "added",
        "said_set_added": "set added",
        # ── 음성 주문 결과 ──
        "engine_smart": "Smart parser",
        "voice_added": "Added {n}",
        "not_understood": "Could not understand",
        "set_word": "set",
        "voice_item_tts": "{qty} {name}",
        "voice_result_tts": "Added {items}. Your total is {total} won.",
        "cleared_tts": "Your cart is now empty.",
        # ── 음성 주문 창(voice_dialog) ──
        "voice_title": "Voice Order",
        "voice_natural": "Order in natural language",
        "examples_label": "Examples:",
        "speak": "Speak",
        "mic_na": "Mic N/A",
        "mic_hint": "Mic: install SpeechRecognition + PyAudio to enable",
        "cancel": "Cancel",
        "analyze": "Analyze",
        "listening_now": "Listening…",
        "speak_again": "Speak again",
        "heard": "✅ Heard: ",
        "calibrating": "🤫 Calibrating noise…",
        "speak_now": "🎙 Speak now! Listening…",
        "recognizing": "🧠 Recognizing…",
        "no_speech": "No speech detected. Please try again.",
        "cannot_understand": "Could not understand.",
        "cannot_understand_clear": "Could not understand the audio.",
        "internet_required": "Internet required. Type or pick an example.",
        "mic_lib_missing": "Speech library missing",
        "error_label": "Error",
        "voice_gesture_hint": ("🤏 Pinch to confirm  ·  👈👉 Swipe to change example\n"
                               "👆 Hold your hand still over a button to click it"),
        # ── 시작 접근성 안내(시각장애인·저시력자) ──
        "a11y_ask_title": "Voice Assistance",
        "a11y_ask": ("Is it hard for you to see the screen?\n\n"
                     "Say 'yes' or press the 'Yes' button below "
                     "to switch to high contrast and order by voice."),
        "a11y_ask_tts": ("Hello. Is it hard for you to see the screen? "
                         "If so, please say yes, or press the Yes button on the screen. "
                         "I will help you order by voice."),
        "a11y_yes": "Yes, order by voice",
        "a11y_no": "No, order on screen",
        "a11y_not_heard_tts": ("Sorry, I could not hear you. Please press the big Yes button, "
                               "or pinch your thumb and index finger together."),
        # ── 음성 주문 안내(TTS) ──
        "voice_guide_tts": ("Starting voice ordering. "
                            "When the microphone turns on, please say the menu you want."),
        "voice_listen_tts": "The microphone is on. Please say your order now.",
        "voice_next_tts": "To order more, just say it. To pay, say checkout.",
        "voice_retry_hint_tts": ("I could not hear you. Press the microphone button, "
                                 "or pinch it, and try again."),
        "voice_heard_tts": ("I heard: {text}. "
                            "To order, press the Analyze button or pinch your thumb and index finger."),
    },
    "zh": {
        # ── 환영 / 기본 ──
        "store_name": "无忧汉堡",
        "welcome_title": "欢迎光临！",
        "welcome_sub": "请触摸屏幕，或用手势 · 语音点单",
        "start_order": "开始点单",
        "cart": "购物车",
        "cart_empty": "购物车是空的",
        "total": "合计",
        "checkout": "结账",
        "clear": "全部清空",
        "add": "加入",
        "set_toggle": "套餐",
        "single": "单点",
        "voice_order": "语音点单",
        "voice_hint": "例）一份烤肉汉堡套餐，可乐换成大杯",
        "listening": "正在聆听...",
        "silver_mode": "大字模式",
        "child_mode": "儿童模式",
        "standard_mode": "标准模式",
        "contrast_mode": "高对比模式",
        "thank_you": "感谢您的惠顾！",
        "order_number": "订单号",
        "best_menu": "人气菜单",
        "won": "韩元",
        "qty": "数量",
        "gesture_on": "手势已开",
        "voice_on": "语音已开",
        "next": "下一个",
        "prev": "上一个",
        "back": "返回",
        "category_pick": "请挑选菜单",
        "added_toast": "已加入",
        # ── 시연 도구막대 ──
        "demo_tools": "演示工具：",
        "demo_grab": "抓取",
        # ── 상태바 / 비전 ──
        "vision_preparing": "📷 视觉 AI 启动中…",
        "vision_demo": "📷 演示模式（使用演示工具）",
        "vision_running": "📷 视觉 AI 运行中（人脸/手势）",
        "vision_stopped": "📷 视觉 AI 已停止",
        "vision_interrupted": "📷 视觉已中断（切换演示模式）",
        "vision_demo_no_opencv": "📷 演示模式（缺少 OpenCV）",
        "vision_demo_no_mediapipe": "📷 演示模式（缺少 MediaPipe 接口）",
        "vision_demo_no_camera": "📷 演示模式（未找到摄像头）",
        "vision_demo_init_fail": "📷 演示模式（视觉模型初始化失败）",
        # ── 손동작 ──
        "gesture_tooltip": "开启/关闭手势控制",
        "gesture_off": "关闭",
        "gesture_on_toast": "✋ 手势控制已开启",
        "gesture_off_toast": "🚫 手势已关闭（请触摸屏幕点单）",
        "point_then_fist": "👉 将光标移到菜单或按钮上，然后🤏捏合手指",
        "nothing_to_scroll": "列表已全部显示，无需滚动",
        # ── 고대비(저시력자) ──
        "contrast_tooltip": "为视力不佳的用户开启/关闭高对比画面",
        # ── 竖屏（底部无障碍按钮 · 欢迎提示）──
        "sound_btn": "语音提示",
        "gesture_btn": "手势",
        "welcome_hint": "✋ 向摄像头展示手掌即可出现手势光标，在按钮上🤏捏合（拇指碰食指）或停留片刻即可按下。",
        # ── 모드 음성 안내(TTS) ──
        "mode_silver_say": "已切换到大字银发模式",
        "mode_child_say": "已切换到儿童模式",
        "mode_contrast_say": "已切换到高对比模式",
        "mode_standard_say": "标准模式",
        # ── 담기 음성 안내 ──
        "said_added": "已加入",
        "said_set_added": "套餐已加入",
        # ── 음성 주문 결과 ──
        "engine_smart": "智能解析",
        "voice_added": "已加入{n}个",
        "not_understood": "没听清菜单",
        "set_word": "套餐",
        "voice_item_tts": "{qty}个{name}",
        "voice_result_tts": "已加入{items}。现在合计{total}韩元。",
        "cleared_tts": "购物车已清空。",

        # ── 음성 주문 창(voice_dialog) ──
        "voice_title": "语音点单",
        "voice_natural": "用自然语言点单",
        "examples_label": "示例：",
        "speak": "说话",
        "mic_na": "麦克风不可用",
        "mic_hint": "麦克风功能：安装 SpeechRecognition + PyAudio 后可用",
        "cancel": "取消",
        "analyze": "分析订单",
        "listening_now": "聆听中…",
        "speak_again": "再说一次",
        "heard": "✅ 已识别：",
        "calibrating": "🤫 正在测量环境噪音…",
        "speak_now": "🎙 请说话！正在聆听…",
        "recognizing": "🧠 正在识别…",
        "no_speech": "没有听到声音，请再试一次。",
        "cannot_understand": "没有听懂。",
        "cannot_understand_clear": "没有听懂，请说清楚一些。",
        "internet_required": "需要联网。请手动输入或点击示例。",
        "mic_lib_missing": "缺少语音库",
        "error_label": "错误",
        "voice_gesture_hint": ("🤏 捏合手指确认  ·  👈👉 左右滑动切换示例\n"
                               "👆 手停在按钮上片刻即可自动点击"),
        # ── 시작 접근성 안내(시각장애인·저시력자) ──
        "a11y_ask_title": "语音辅助",
        "a11y_ask": ("您看不清屏幕吗？\n\n"
                     "说“是”或按下方的“是”按钮，"
                     "即可切换为高对比画面并通过语音点单。"),
        "a11y_ask_tts": ("您好。您看不清屏幕吗？"
                         "如果是，请说是，或按屏幕上的是按钮。"
                         "我将用语音帮您点单。"),
        "a11y_yes": "是，用语音点单",
        "a11y_no": "不，用屏幕点单",
        "a11y_not_heard_tts": "抱歉，没有听清。请按下屏幕上的大按钮“是”，或者将拇指和食指捏在一起。",
        # ── 음성 주문 안내(TTS) ──
        "voice_guide_tts": ("开始语音点单。"
                            "麦克风开启后，请说出您想要的菜单。"),
        "voice_listen_tts": "麦克风已开启。请现在说出您的订单。",
        "voice_next_tts": "如需继续点单请直接说，结账请说结账。",
        "voice_retry_hint_tts": "没有听清。请按麦克风按钮或用捏合手势按下，再说一次。",
        "voice_heard_tts": ("我听到的是：{text}。"
                            "要下单，请按分析按钮或将拇指和食指捏在一起。"),
    },
}


def next_lang(lang: str) -> str:
    """현재 언어의 '다음 언어'를 돌려줍니다(ko → en → zh → ko)."""
    try:
        i = LANG_ORDER.index(lang)
    except ValueError:
        return LANG_ORDER[0]
    return LANG_ORDER[(i + 1) % len(LANG_ORDER)]


class Translator:
    """현재 언어를 기억하고 글자를 돌려주는 작은 도우미."""

    def __init__(self, lang: str = "ko"):
        self.lang = lang if lang in TEXTS else "ko"

    def set_lang(self, lang: str) -> None:
        if lang in TEXTS:
            self.lang = lang

    def t(self, key: str) -> str:
        return TEXTS.get(self.lang, TEXTS["ko"]).get(key, key)
