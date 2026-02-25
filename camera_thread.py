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
    error_signal = pyqtSignal(str)  # 🔥 에러 전달용 시그널 추가

    def __init__(self, camera_index=0, target_width=1920, target_height=1080):
        super().__init__()
        self.camera_index = camera_index
        self.target_width = target_width
        self.target_height = target_height
        self._run_flag = True

    def run(self):
        # 🔥 플랫폼별 백엔드 설정
        if platform.system() == 'Darwin':  # macOS
            # AVFoundation 사용 (Canon EOS Webcam Utility 지원)
            cap = cv2.VideoCapture(self.camera_index, cv2.CAP_AVFOUNDATION)
        elif platform.system() == 'Windows':
            # DirectShow 사용
            cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        else:
            # Linux 등
            cap = cv2.VideoCapture(self.camera_index)
        
        # 🔥 카메라 열기 실패 처리
        if not cap.isOpened():
            error_msg = f"❌ 카메라 #{self.camera_index} 열기 실패!\n\n"
            error_msg += "해결방법:\n"
            error_msg += "1. Canon EOS Webcam Utility가 설치되어 있는지 확인\n"
            error_msg += "2. 카메라가 USB로 연결되어 있는지 확인\n"
            error_msg += "3. 카메라를 동영상 모드로 설정\n"
            error_msg += "4. check_camera.py로 올바른 인덱스 확인"
            self.error_signal.emit(error_msg)
            return
        
        # 🔥 해상도 설정 시도
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.target_width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.target_height)
        
        # 실제 설정된 해상도 확인
        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"[Camera] 요청 해상도: {self.target_width}x{self.target_height}")
        print(f"[Camera] 실제 해상도: {actual_w}x{actual_h}")
        
        # 🔥 Canon R100은 보통 1920x1080을 지원하지만, 확인 필요
        if actual_w != self.target_width or actual_h != self.target_height:
            print(f"⚠️ 해상도 불일치! 카메라가 지원하는 해상도로 작동합니다.")

        frame_count = 0
        while self._run_flag:
            ret, cv_img = cap.read()
            
            if not ret:
                print(f"⚠️ 프레임 읽기 실패 (frame #{frame_count})")
                continue
            
            # 1. BGR -> RGB 변환
            rgb_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
            
            # 2. PyQt용 QImage로 변환
            h, w, ch = rgb_img.shape
            bytes_per_line = ch * w
            convert_to_qt_format = QImage(
                rgb_img.data, 
                w, 
                h, 
                bytes_per_line, 
                QImage.Format.Format_RGB888
            )
            
            # 3. 메인 쓰레드로 이미지 전송 (30fps 제한)
            self.change_pixmap_signal.emit(convert_to_qt_format.copy())
            
            frame_count += 1
            self.msleep(33)  # 약 30fps로 제한
        
        # 종료 시 카메라 해제
        print(f"[Camera] 총 {frame_count}프레임 처리 완료")
        cap.release()

    def stop(self):
        """쓰레드 종료 플래그 설정"""
        print("[Camera] 종료 요청됨")
        self._run_flag = False
        self.wait()
        print("[Camera] 종료 완료")


# 🔥 카메라 지원 해상도 확인 함수
def get_supported_resolutions(camera_index=0):
    """
    카메라가 지원하는 해상도 목록 반환
    """
    cap = cv2.VideoCapture(camera_index)
    
    if not cap.isOpened():
        print(f"❌ 카메라 #{camera_index} 열기 실패")
        return []
    
    # 일반적인 해상도 목록
    test_resolutions = [
        (640, 480),    # VGA
        (1280, 720),   # HD
        (1920, 1080),  # Full HD
        (2560, 1440),  # QHD
        (3840, 2160),  # 4K
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