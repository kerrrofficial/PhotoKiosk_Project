"""
camera_manager.py
캡처보드 프리뷰 + USB 테더링 촬영 통합 관리

사용법:
    manager = CameraManager(
        preview_camera_index=1,  # 캡처보드
        preview_width=640,
        preview_height=480
    )
    
    # 프리뷰 시작
    manager.start_preview()
    
    # 촬영
    filepath = manager.capture_photo()
    
    # 프리뷰 종료
    manager.stop_preview()
"""

import os
import time
import logging
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal
from camera_thread import VideoThread
from shutter_trigger import EOSRemoteShutter
from tether_service import WATCH_DIR, _list_media_files, SUPPORTED_EXT

# 🔥 로그 파일 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('camera_manager.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class CameraManager(QObject):
    """
    하이브리드 카메라 시스템 관리
    - 프리뷰: 캡처보드 (VideoThread)
    - 촬영: USB 테더링 (EOSRemoteShutter)
    """
    
    # 시그널
    preview_frame_ready = pyqtSignal(object)  # QImage
    photo_captured = pyqtSignal(str)  # 파일 경로
    capture_failed = pyqtSignal(str)  # 에러 메시지
    
    def __init__(
        self,
        preview_camera_index=1,
        preview_width=640,
        preview_height=480,
        capture_timeout=10
    ):
        super().__init__()
        
        # 설정
        self.preview_camera_index = preview_camera_index
        self.preview_width = preview_width
        self.preview_height = preview_height
        self.capture_timeout = capture_timeout
        
        # 프리뷰 스레드
        self.preview_thread = None
        
        # 촬영 컨트롤러
        self.shutter = EOSRemoteShutter()
        
        # 세션 관리
        self.session_dir = None
        self.captured_files = []
        
        logger.info("=" * 60)
        logger.info("[CameraManager] 초기화 완료")
        logger.info(f"  - 프리뷰 카메라: #{preview_camera_index}")
        logger.info(f"  - 프리뷰 해상도: {preview_width}x{preview_height}")
        logger.info("=" * 60)
    
    def start_preview(self):
        """
        캡처보드 프리뷰 시작
        """
        if self.preview_thread is not None:
            print("[CameraManager] 프리뷰가 이미 실행 중입니다.")
            return
        
        print("[CameraManager] 프리뷰 시작...")
        
        # VideoThread 생성
        self.preview_thread = VideoThread(
            camera_index=self.preview_camera_index,
            target_width=self.preview_width,
            target_height=self.preview_height
        )
        
        # 시그널 연결
        self.preview_thread.change_pixmap_signal.connect(
            self._on_preview_frame
        )
        self.preview_thread.error_signal.connect(
            self._on_preview_error
        )
        
        # 스레드 시작
        self.preview_thread.start()
        
        print("[CameraManager] ✅ 프리뷰 시작됨")
    
    def stop_preview(self):
        """
        캡처보드 프리뷰 중지
        """
        if self.preview_thread is None:
            return
        
        print("[CameraManager] 프리뷰 중지...")
        
        self.preview_thread.stop()
        self.preview_thread.wait()
        self.preview_thread = None
        
        print("[CameraManager] ✅ 프리뷰 중지됨")
    
    def _on_preview_frame(self, qimage):
        """
        프리뷰 프레임 수신 (내부용)
        """
        self.preview_frame_ready.emit(qimage)
    
    def _on_preview_error(self, error_msg):
        """
        프리뷰 에러 처리 (내부용)
        """
        print(f"[CameraManager] 프리뷰 에러: {error_msg}")
        self.capture_failed.emit(error_msg)
    
    def capture_photo(self) -> str | None:
        """
        테더링 촬영 (블로킹 방식)
        
        Returns:
            촬영된 파일 경로 또는 None
        """
        logger.info("=" * 60)
        logger.info("[CameraManager] 📸 촬영 시작...")
        
        # 1. 촬영 전 파일 목록 스냅샷
        WATCH_DIR.mkdir(exist_ok=True)
        before_files = {f.name for f in _list_media_files(WATCH_DIR)}
        logger.info(f"[CameraManager] 촬영 전 파일 수: {len(before_files)}개")
        logger.info(f"[CameraManager] 감시 폴더: {WATCH_DIR.resolve()}")
        logger.info(f"[CameraManager] 촬영 전 파일 목록: {before_files}")
        
        # 2. 셔터 트리거
        logger.info("[CameraManager] 셔터 트리거 호출...")
        if not self.shutter.trigger(wait_after=2.0, auto_activate=True):
            error_msg = "셔터 트리거 실패"
            logger.error(f"[CameraManager] ❌ {error_msg}")
            self.capture_failed.emit(error_msg)
            return None
        
        logger.info("[CameraManager] 셔터 트리거 완료, 파일 대기 시작")
        
        # 3. 새 파일 대기
        new_file = self._wait_for_new_file(
            before_files,
            timeout=self.capture_timeout
        )
        
        if new_file is None:
            error_msg = f"촬영 타임아웃 ({self.capture_timeout}초)"
            logger.error(f"[CameraManager] ❌ {error_msg}")
            
            # 디버깅: 현재 파일 목록 출력
            current_files = _list_media_files(WATCH_DIR)
            logger.info(f"[CameraManager] 타임아웃 후 파일 수: {len(current_files)}개")
            if current_files:
                logger.info("[CameraManager] 발견된 파일들:")
                for f in current_files:
                    logger.info(f"  - {f.name}")
            
            self.capture_failed.emit(error_msg)
            return None
        
        # 4. 세션 폴더로 복사
        if self.session_dir is None:
            self._create_session()
        
        dest_path = self.session_dir / new_file.name
        dest_path.write_bytes(new_file.read_bytes())
        
        self.captured_files.append(str(dest_path))
        
        logger.info(f"[CameraManager] ✅ 촬영 완료: {dest_path.name}")
        logger.info("=" * 60)
        self.photo_captured.emit(str(dest_path))
        
        return str(dest_path)
    
    def _wait_for_new_file(self, before_files: set, timeout: float) -> Path | None:
        """
        새 파일이 생성될 때까지 대기
        
        Args:
            before_files: 촬영 전 파일명 세트
            timeout: 대기 시간(초)
        
        Returns:
            새 파일 경로 또는 None
        """
        end_time = time.time() + timeout
        check_count = 0
        
        logger.info(f"[CameraManager] 파일 감지 시작 (타임아웃: {timeout}초)")
        
        while time.time() < end_time:
            check_count += 1
            current_files = _list_media_files(WATCH_DIR)
            
            # 현재 파일 목록 출력 (10회마다)
            if check_count % 10 == 0:
                current_names = {f.name for f in current_files}
                logger.info(f"[CameraManager] 체크 #{check_count}: 현재 파일 {len(current_names)}개")
                new_files = current_names - before_files
                if new_files:
                    logger.info(f"[CameraManager] 새 파일 후보: {new_files}")
            
            for f in current_files:
                if f.name in before_files:
                    continue
                
                logger.info(f"[CameraManager] 🔍 새 파일 감지: {f.name}")
                
                # 파일 쓰기 완료 확인
                try:
                    size1 = f.stat().st_size
                except FileNotFoundError:
                    logger.warning(f"[CameraManager] 파일 사라짐: {f.name}")
                    continue
                
                if size1 <= 0:
                    logger.warning(f"[CameraManager] 파일 크기 0: {f.name}")
                    continue
                
                logger.info(f"[CameraManager] 파일 크기 확인: {size1} bytes, 0.3초 대기...")
                time.sleep(0.3)
                
                try:
                    size2 = f.stat().st_size
                except FileNotFoundError:
                    logger.warning(f"[CameraManager] 파일 사라짐 (2차): {f.name}")
                    continue
                
                # 파일 크기가 안정적이면 완료
                if size2 == size1 and size2 > 0:
                    logger.info(f"[CameraManager] ✅ 파일 안정화 완료: {f.name} ({size2} bytes)")
                    return f
                else:
                    logger.info(f"[CameraManager] 파일 쓰기 중: {size1} → {size2} bytes")
            
            time.sleep(0.2)
        
        logger.error(f"[CameraManager] ❌ 타임아웃! 총 {check_count}회 체크")
        return None
    
    def _create_session(self):
        """
        세션 폴더 생성
        """
        from datetime import datetime
        
        sessions_dir = Path("sessions")
        sessions_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = sessions_dir / f"session_{timestamp}"
        self.session_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"[CameraManager] 세션 생성: {self.session_dir}")
    
    def start_session(self):
        """
        새 촬영 세션 시작
        """
        self._create_session()
        self.captured_files = []
        print("[CameraManager] 새 세션 시작")
    
    def get_captured_files(self) -> list[str]:
        """
        현재 세션에서 촬영된 파일 목록
        """
        return self.captured_files.copy()
    
    def cleanup(self):
        """
        정리 작업
        """
        self.stop_preview()
        print("[CameraManager] 정리 완료")


# ============================================================
# 테스트 코드
# ============================================================

def test_preview_only():
    """프리뷰만 테스트"""
    from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow
    from PyQt6.QtCore import Qt
    import sys
    
    print("\n" + "="*60)
    print("프리뷰 테스트")
    print("="*60)
    
    app = QApplication(sys.argv)
    
    # 메인 윈도우
    window = QMainWindow()
    window.setWindowTitle("캡처보드 프리뷰 테스트")
    window.resize(800, 600)
    
    # 프리뷰 라벨
    label = QLabel()
    label.setScaledContents(True)
    window.setCentralWidget(label)
    
    # 카메라 매니저
    manager = CameraManager(
        preview_camera_index=1,  # 캡처보드
        preview_width=640,
        preview_height=480
    )
    
    # 프레임 업데이트
    def update_preview(qimage):
        from PyQt6.QtGui import QPixmap
        pixmap = QPixmap.fromImage(qimage)
        label.setPixmap(pixmap)
    
    manager.preview_frame_ready.connect(update_preview)
    
    # 프리뷰 시작
    manager.start_preview()
    
    window.show()
    
    print("\n✅ 프리뷰 창이 열렸습니다.")
    print("💡 Canon R100 화면이 보여야 합니다.")
    print("⌨️  창을 닫으면 종료됩니다.\n")
    
    result = app.exec()
    
    manager.cleanup()
    sys.exit(result)


def test_capture_only():
    """촬영만 테스트 (프리뷰 없음)"""
    print("\n" + "="*60)
    print("촬영 테스트 (프리뷰 없음)")
    print("="*60)
    
    manager = CameraManager(preview_camera_index=1, capture_timeout=15)
    
    print("\n⚠️ 준비사항:")
    print("  1. EOS Utility 실행 중")
    print("  2. 원격 라이브 뷰 창 열려있음")
    print("  3. 저장 폴더: incoming_photos/")
    
    # incoming_photos 폴더 확인
    from pathlib import Path
    watch_dir = Path("incoming_photos")
    watch_dir.mkdir(exist_ok=True)
    
    existing_files = list(watch_dir.glob("*.JPG")) + list(watch_dir.glob("*.jpg"))
    print(f"\n현재 incoming_photos/ 파일 수: {len(existing_files)}개")
    
    print("\n3초 후 촬영을 시작합니다...")
    time.sleep(3)
    
    # 촬영
    manager.start_session()
    print(f"\n세션 폴더: {manager.session_dir}")
    
    filepath = manager.capture_photo()
    
    if filepath:
        print(f"\n✅ 촬영 성공!")
        print(f"파일: {filepath}")
    else:
        print(f"\n❌ 촬영 실패")
        print(f"\n디버깅 정보:")
        print(f"  - EOS Utility 저장 폴더가 incoming_photos/인지 확인하세요")
        print(f"  - 수동으로 촬영해서 파일이 생성되는지 확인하세요")
    
    manager.cleanup()


def test_full_workflow():
    """프리뷰 + 촬영 통합 테스트"""
    from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget
    from PyQt6.QtCore import Qt
    import sys
    
    print("\n" + "="*60)
    print("프리뷰 + 촬영 통합 테스트")
    print("="*60)
    
    app = QApplication(sys.argv)
    
    # 메인 윈도우
    window = QMainWindow()
    window.setWindowTitle("하이브리드 카메라 테스트")
    window.resize(800, 700)
    
    # 중앙 위젯
    central = QWidget()
    layout = QVBoxLayout(central)
    
    # 프리뷰 라벨
    label = QLabel()
    label.setScaledContents(True)
    label.setMinimumSize(640, 480)
    layout.addWidget(label)
    
    # 촬영 버튼
    btn = QPushButton("📸 촬영하기")
    btn.setMinimumHeight(60)
    layout.addWidget(btn)
    
    window.setCentralWidget(central)
    
    # 카메라 매니저
    manager = CameraManager(
        preview_camera_index=1,
        preview_width=640,
        preview_height=480,
        capture_timeout=10
    )
    
    # 프레임 업데이트
    def update_preview(qimage):
        from PyQt6.QtGui import QPixmap
        pixmap = QPixmap.fromImage(qimage)
        label.setPixmap(pixmap)
    
    manager.preview_frame_ready.connect(update_preview)
    
    # 촬영 버튼 클릭
    def on_capture():
        btn.setEnabled(False)
        btn.setText("촬영 중...")
        
        print("\n[테스트] 촬영 시작...")
        filepath = manager.capture_photo()
        
        if filepath:
            print(f"[테스트] ✅ 촬영 성공: {filepath}")
            btn.setText(f"✅ 촬영 완료! (총 {len(manager.captured_files)}장)")
        else:
            print(f"[테스트] ❌ 촬영 실패")
            btn.setText("❌ 촬영 실패")
        
        # 1초 후 버튼 활성화
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(1000, lambda: btn.setEnabled(True))
        QTimer.singleShot(1000, lambda: btn.setText("📸 촬영하기"))
    
    btn.clicked.connect(on_capture)
    
    # 세션 시작
    manager.start_session()
    
    # 프리뷰 시작
    manager.start_preview()
    
    window.show()
    
    print("\n✅ 테스트 창이 열렸습니다.")
    print("💡 프리뷰를 확인하고 '촬영하기' 버튼을 누르세요!")
    print("⌨️  창을 닫으면 종료됩니다.\n")
    
    result = app.exec()
    
    manager.cleanup()
    
    print(f"\n촬영된 파일 ({len(manager.captured_files)}장):")
    for f in manager.captured_files:
        print(f"  - {f}")
    
    sys.exit(result)


def run_standalone_mode():
    """
    독립 실행 모드: 8장 촬영 후 camera_result.json 생성
    """
    import json
    from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton
    from PyQt6.QtCore import QTimer
    from PyQt6.QtGui import QPixmap
    import sys
    
    print("\n🎥 독립 촬영 모드 시작")
    print("=" * 60)
    
    app = QApplication(sys.argv)
    
    # 카메라 매니저 생성
    manager = CameraManager(
        preview_camera_index=1,
        preview_width=640,
        preview_height=480,
        capture_timeout=15
    )
    
    # 메인 윈도우
    window = QMainWindow()
    window.setWindowTitle("네컷사진 촬영 (8장)")
    window.resize(1280, 900)
    
    central = QWidget()
    layout = QVBoxLayout(central)
    
    # 프리뷰 라벨
    label = QLabel()
    label.setScaledContents(True)
    label.setMinimumSize(1280, 720)
    layout.addWidget(label)
    
    # 진행 상태
    status_label = QLabel("0/8 촬영 완료")
    status_label.setStyleSheet("font-size: 32px; font-weight: bold;")
    layout.addWidget(status_label)
    
    # 촬영 버튼
    btn = QPushButton("📸 촬영 시작")
    btn.setMinimumHeight(80)
    btn.setStyleSheet("font-size: 24px;")
    layout.addWidget(btn)
    
    window.setCentralWidget(central)
    
    # 프레임 업데이트
    def update_preview(qimage):
        pixmap = QPixmap.fromImage(qimage)
        label.setPixmap(pixmap)
    
    manager.preview_frame_ready.connect(update_preview)
    
    # 세션 시작
    manager.start_session()
    manager.start_preview()
    
    # 촬영 카운터
    shot_count = 0
    total_shots = 8
    
    # 촬영 버튼 클릭
    def on_capture():
        nonlocal shot_count
        
        btn.setEnabled(False)
        btn.setText("📸 촬영 중...")
        
        filepath = manager.capture_photo()
        
        if filepath:
            shot_count += 1
            status_label.setText(f"{shot_count}/{total_shots} 촬영 완료")
            print(f"[촬영] {shot_count}/{total_shots} - {filepath}")
            
            if shot_count >= total_shots:
                # 촬영 완료
                save_result_and_exit()
            else:
                # 다음 촬영 준비
                QTimer.singleShot(2000, lambda: btn.setEnabled(True))
                QTimer.singleShot(2000, lambda: btn.setText(f"📸 다음 촬영 ({shot_count}/{total_shots})"))
        else:
            print(f"[촬영] 실패 - 재시도")
            btn.setEnabled(True)
            btn.setText("❌ 재촬영")
    
    btn.clicked.connect(on_capture)
    
    # 결과 저장 및 종료
    def save_result_and_exit():
        btn.setText("✅ 촬영 완료!")
        status_label.setText("저장 중...")
        
        # 촬영된 파일 목록을 JSON으로 저장
        result = {
            'success': True,
            'files': manager.get_captured_files(),
            'session_dir': str(manager.session_dir)
        }
        
        result_path = 'camera_result.json'
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"\n✅ 결과 저장: {result_path}")
        print(f"촬영된 파일: {len(result['files'])}개")
        for f in result['files']:
            print(f"  - {f}")
        
        status_label.setText("완료! 2초 후 종료됩니다.")
        
        # 2초 후 종료
        QTimer.singleShot(2000, app.quit)
    
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    import sys
    
    # 🔥 독립 실행 모드 체크
    if len(sys.argv) > 1 and sys.argv[1] == '--standalone':
        # 독립 촬영 모드
        run_standalone_mode()
    else:
        # 기존 테스트 모드
        print("\n🎯 카메라 매니저 테스트")
        print("\n옵션:")
        print("  1) 프리뷰만 테스트")
        print("  2) 촬영만 테스트")
        print("  3) 프리뷰 + 촬영 통합 테스트 (권장)")
        
        choice = input("\n선택 (1-3): ").strip()
        
        if choice == "1":
            test_preview_only()
        elif choice == "2":
            test_capture_only()
        elif choice == "3":
            test_full_workflow()
        else:
            print("❌ 잘못된 선택")