import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QImage

class VideoThread(QThread):
    # 카메라 영상을 메인 화면으로 보내는 신호 (이미지 데이터 전송용)
    change_pixmap_signal = pyqtSignal(QImage)

    def __init__(self):
        super().__init__()
        self._run_flag = True

    def run(self):
        # 웹캠 캡처 시작 (0번 카메라)
        cap = cv2.VideoCapture(0)
        
        # 해상도 설정 (FHD 권장)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

        while self._run_flag:
            ret, cv_img = cap.read()
            if ret:
                # 1. BGR -> RGB 변환
                rgb_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
                
                # 2. PyQt용 QImage로 변환
                h, w, ch = rgb_img.shape
                bytes_per_line = ch * w
                convert_to_qt_format = QImage(rgb_img.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                
                # 3. 화면 비율에 맞게 리사이징 (선택 사항, 성능 최적화용)
                # p = convert_to_qt_format.scaled(640, 480, Qt.AspectRatioMode.KeepAspectRatio)
                
                # 4. 메인 쓰레드로 이미지 전송
                self.change_pixmap_signal.emit(convert_to_qt_format)
        
        # 종료 시 카메라 해제
        cap.release()

    def stop(self):
        """쓰레드 종료 플래그 설정"""
        self._run_flag = False
        self.wait()