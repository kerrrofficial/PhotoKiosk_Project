from PyQt6.QtCore import QThread, pyqtSignal
from tether_service import capture_many_photos_blocking

class TetherCaptureManyThread(QThread):
    success = pyqtSignal(list)  # 사진 경로 리스트(str 리스트로 보내도 되지만 일단 list)
    failed = pyqtSignal(str)

    def __init__(self, expected_count=8, timeout_sec=45, parent=None):
        super().__init__(parent)
        self.expected_count = expected_count
        self.timeout_sec = timeout_sec

    def run(self):
        try:
            paths = capture_many_photos_blocking(
                expected_count=self.expected_count,
                timeout_sec=self.timeout_sec
            )
            if paths and len(paths) >= self.expected_count:
                self.success.emit([str(p) for p in paths])
            else:
                self.failed.emit(f"Captured {len(paths)} / {self.expected_count} (timeout)")
        except Exception as e:
            self.failed.emit(str(e))
