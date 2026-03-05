import cv2
import numpy as np
import platform
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QImage

class VideoThread(QThread):
    """
    카메라 영상을 메인 화면으로 보내는 스레드
    Canon R100 등 외부 카메라 지원
    """
    change_pixmap_signal = pyqtSignal(QImage)
    error_signal = pyqtSignal(str)
    reconnect_signal = pyqtSignal(str)  # 재연결 상태 알림용

    # 재연결 설정
    MAX_FAIL_COUNT = 5        # 연속 실패 허용 횟수
    RECONNECT_INTERVAL = 10   # 재연결 시도 간격 (초)
    MAX_RECONNECT_TRY = 10    # 최대 재연결 시도 횟수 (0 = 무한)

    def __init__(self, camera_index=0, target_width=1920, target_height=1080):
        super().__init__()
        self.camera_index = camera_index
        self.target_width = target_width
        self.target_height = target_height
        self._run_flag = True

    def _open_camera(self):
        """카메라 열기 (플랫폼별)"""
        if platform.system() == 'Darwin':
            cap = cv2.VideoCapture(self.camera_index, cv2.CAP_AVFOUNDATION)
        elif platform.system() == 'Windows':
            cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        else:
            cap = cv2.VideoCapture(self.camera_index)

        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.target_width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.target_height)
            actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            print(f"[Camera] 요청 해상도: {self.target_width}x{self.target_height}")
            print(f"[Camera] 실제 해상도: {actual_w}x{actual_h}")

        return cap

    def run(self):
        cap = self._open_camera()

        if not cap.isOpened():
            error_msg = f"❌ 카메라 #{self.camera_index} 열기 실패!\n\n"
            error_msg += "해결방법:\n"
            error_msg += "1. 캡처보드가 연결되어 있는지 확인\n"
            error_msg += "2. 카메라 HDMI 케이블 확인\n"
            error_msg += "3. 카메라를 동영상 모드로 설정"
            self.error_signal.emit(error_msg)
            return

        frame_count = 0
        fail_count = 0          # 연속 실패 횟수
        reconnect_count = 0     # 재연결 시도 횟수

        while self._run_flag:
            ret, cv_img = cap.read()

            if not ret:
                fail_count += 1
                print(f"⚠️ 프레임 읽기 실패 ({fail_count}/{self.MAX_FAIL_COUNT}) - frame #{frame_count}")

                # 연속 실패가 임계값 초과 시 재연결 시도
                if fail_count >= self.MAX_FAIL_COUNT:
                    reconnect_count += 1
                    print(f"[Camera] 🔄 재연결 시도 #{reconnect_count}...")
                    self.reconnect_signal.emit(f"카메라 재연결 중... ({reconnect_count}회)")

                    cap.release()
                    self.msleep(self.RECONNECT_INTERVAL * 1000)

                    cap = self._open_camera()

                    if cap.isOpened():
                        print(f"[Camera] ✅ 재연결 성공! (시도 #{reconnect_count})")
                        self.reconnect_signal.emit("카메라 연결 복구됨")
                        fail_count = 0
                    else:
                        print(f"[Camera] ❌ 재연결 실패 (시도 #{reconnect_count})")
                        # MAX_RECONNECT_TRY가 0이면 무한 재시도
                        if self.MAX_RECONNECT_TRY > 0 and reconnect_count >= self.MAX_RECONNECT_TRY:
                            print(f"[Camera] ❌ 최대 재연결 시도 초과 - 종료")
                            self.error_signal.emit("카메라 연결 실패\n캡처보드와 카메라 연결을 확인해주세요.")
                            break
                else:
                    # 임계값 미달 시 짧게 대기 후 재시도
                    self.msleep(500)

                continue

            # 프레임 읽기 성공 시 fail_count 초기화
            if fail_count > 0:
                print(f"[Camera] ✅ 프레임 복구됨 (실패 {fail_count}회 후)")
                fail_count = 0
                reconnect_count = 0

            # BGR -> RGB 변환
            rgb_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)

            # PyQt용 QImage로 변환
            h, w, ch = rgb_img.shape
            bytes_per_line = ch * w
            convert_to_qt_format = QImage(
                rgb_img.data,
                w,
                h,
                bytes_per_line,
                QImage.Format.Format_RGB888
            )

            # 메인 스레드로 이미지 전송
            self.change_pixmap_signal.emit(convert_to_qt_format.copy())

            frame_count += 1
            self.msleep(33)  # 약 30fps

        print(f"[Camera] 총 {frame_count}프레임 처리 완료")
        cap.release()

    def stop(self):
        """스레드 종료"""
        print("[Camera] 종료 요청됨")
        self._run_flag = False
        self.wait()
        print("[Camera] 종료 완료")


# 카메라 지원 해상도 확인 함수
def get_supported_resolutions(camera_index=0):
    cap = cv2.VideoCapture(camera_index)

    if not cap.isOpened():
        print(f"❌ 카메라 #{camera_index} 열기 실패")
        return []

    test_resolutions = [
        (640, 480),
        (1280, 720),
        (1920, 1080),
        (2560, 1440),
        (3840, 2160),
    ]

    supported = []

    for w, h in test_resolutions:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if (actual_w, actual_h) not in supported:
            supported.append((actual_w, actual_h))

    cap.release()

    print(f"\n카메라 #{camera_index} 지원 해상도:")
    for w, h in supported:
        print(f"  - {w} x {h}")

    return supported
