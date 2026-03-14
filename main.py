import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision
import time
import math
import win32gui
import win32con


PINCH_THRESHOLD = 0.07
COOLDOWN = 0.35


HAND_CONNECTIONS = [
    (0, 1), (0, 5), (0, 17),
    (5, 9), (9, 13), (13, 17),
    (1, 2), (2, 3), (3, 4),
    (5, 6), (6, 7), (7, 8),
    (9, 10), (10, 11), (11, 12),
    (13, 14), (14, 15), (15, 16),
    (17, 18), (18, 19), (19, 20),
]

FINGERTIPS = {4, 8, 12, 16, 20}

C_LINE  = (0, 255, 120)
C_JOINT = (220, 220, 220)
C_WRIST = (0, 120, 255)
C_TIP   = (0, 60, 255)
C_PINCH = (0, 220, 255)
C_JUMP  = (0, 255, 255)


def find_chrome_window():

    result = []
    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if any(x in title for x in ["Chrome", "chrome", "Dino", "dino", "dinosaur"]):
                result.append((hwnd, title))
    win32gui.EnumWindows(callback, None)
    return result[0][0] if result else None


def send_space_to_chrome(hwnd):

    VK_SPACE = 0x20
    win32gui.SendMessage(hwnd, win32con.WM_KEYDOWN, VK_SPACE, 0)
    time.sleep(0.05)
    win32gui.SendMessage(hwnd, win32con.WM_KEYUP, VK_SPACE, 0)


def dist(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def draw_skeleton(frame, landmarks, w, h, is_pinching):
    pts = {i: (int(lm.x * w), int(lm.y * h)) for i, lm in enumerate(landmarks)}
    line_color = C_PINCH if is_pinching else C_LINE
    for s, e in HAND_CONNECTIONS:
        cv2.line(frame, pts[s], pts[e], line_color, 2, cv2.LINE_AA)
    for i, pt in pts.items():
        if i == 0:
            cv2.circle(frame, pt, 8, C_WRIST, -1, cv2.LINE_AA)
            cv2.circle(frame, pt, 8, (255, 255, 255), 1, cv2.LINE_AA)
        elif i in FINGERTIPS:
            color = C_PINCH if (is_pinching and i in (4, 8)) else C_TIP
            cv2.circle(frame, pt, 7, color, -1, cv2.LINE_AA)
            cv2.circle(frame, pt, 7, (255, 255, 255), 1, cv2.LINE_AA)
        else:
            cv2.circle(frame, pt, 5, C_JOINT, -1, cv2.LINE_AA)
    if is_pinching:
        cv2.line(frame, pts[4], pts[8], C_JUMP, 3, cv2.LINE_AA)


def draw_ui(frame, w, h, is_pinching, last_jump_time, jump_count, chrome_found):
    now = time.time()
    cooldown_left = max(0, COOLDOWN - (now - last_jump_time))
    panel_y = h - 80
    cv2.rectangle(frame, (0, panel_y), (w, h), (20, 20, 20), -1)


    chrome_status = "browser found" if chrome_found else "browser is not open: chrome://dino"
    chrome_color  = (0, 255, 120) if chrome_found else (0, 100, 255)
    cv2.putText(frame, chrome_status, (15, panel_y + 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, chrome_color, 1, cv2.LINE_AA)

    gesture_text  = "jump" if is_pinching else "put your thumb and index finger together"
    gesture_color = C_JUMP if is_pinching else (150, 150, 150)
    cv2.putText(frame, gesture_text, (15, panel_y + 48),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, gesture_color, 2, cv2.LINE_AA)

    bar_w = int((1 - cooldown_left / COOLDOWN) * 200) if cooldown_left > 0 else 200
    cv2.rectangle(frame, (15, panel_y + 58), (215, panel_y + 68), (60, 60, 60), -1)
    cv2.rectangle(frame, (15, panel_y + 58), (15 + bar_w, panel_y + 68), C_JUMP, -1)

    cv2.putText(frame, f"jumps: {jump_count}", (w - 170, panel_y + 48),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1, cv2.LINE_AA)

    cv2.rectangle(frame, (0, 0), (w, 45), (20, 20, 20), -1)
    cv2.putText(frame, "DINOCONTROLLER", (15, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, C_JUMP, 2, cv2.LINE_AA)
    cv2.putText(frame, "q/esc - exit", (w - 165, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (120, 120, 120), 1, cv2.LINE_AA)

    if is_pinching:
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, h), (0, 180, 180), -1)
        cv2.addWeighted(overlay, 0.08, frame, 0.92, 0, frame)


def main():
    try:
        base_options = mp_python.BaseOptions(model_asset_path='hand_landmarker.task')
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            num_hands=1,
            min_hand_detection_confidence=0.6,
            min_hand_presence_confidence=0.6,
            min_tracking_confidence=0.5,
            running_mode=vision.RunningMode.VIDEO
        )
        detector = vision.HandLandmarker.create_from_options(options)
    except Exception as e:
        print(f"ошибка модели: {e}")
        return

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("камера не найдена")
        return

    print("=" * 50)
    print("  DINOCONTROLLER")
    print("=" * 50)
    print("  1. открой chrome://dino")
    print("  2. нажми пробел чтобы начать")
    print("  3. сведи пальцы = прыжок")
    print("     (браузер не надо делать активным)")
    print("=" * 50)

    last_jump_time = 0
    jump_count = 0
    was_pinching = False
    timestamp = 0
    chrome_hwnd = None
    last_chrome_search = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape
        dark = (frame * 0.2).astype(frame.dtype)

        now = time.time()


        if now - last_chrome_search > 2:
            chrome_hwnd = find_chrome_window()
            last_chrome_search = now

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        timestamp += 1
        result = detector.detect_for_video(mp_image, timestamp)

        is_pinching = False

        if result.hand_landmarks:
            lms = result.hand_landmarks[0]
            d = dist(lms[4], lms[8])
            is_pinching = d < PINCH_THRESHOLD
            draw_skeleton(dark, lms, w, h, is_pinching)

            if is_pinching and not was_pinching and (now - last_jump_time) > COOLDOWN:
                if chrome_hwnd:
                    send_space_to_chrome(chrome_hwnd)
                    jump_count += 1
                    last_jump_time = now
                    print(f"   ПРЫЖОК #{jump_count}!")
                else:
                    print("  browser is not open , open it:  chrome://dino")

        was_pinching = is_pinching
        draw_ui(dark, w, h, is_pinching, last_jump_time, jump_count, chrome_hwnd is not None)
        cv2.imshow("dino controller", dark)

        key = cv2.waitKey(1) & 0xFF
        if key in (ord('q'), ord('Q'), 27):
            break

    cap.release()
    cv2.destroyAllWindows()
    detector.close()
    print(f"\njumps amount: {jump_count}")


if __name__ == "__main__":
    main()