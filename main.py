import sys
import os

os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
os.environ["QT_SCALE_FACTOR"] = "1"

import platform
import json
import glob
import random
import subprocess
from datetime import datetime

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QStackedWidget, QGridLayout, QMessageBox, 
                             QSizePolicy, QLineEdit, QCheckBox, QFrame, QScrollArea, QInputDialog, 
                             QDialog, QToolButton, QComboBox, QGraphicsOpacityEffect)
from PyQt6.QtCore import Qt, QTimer, QSize, QRect, pyqtSignal
from PyQt6.QtGui import QPixmap, QIcon, QPainter, QColor, QPen, QPageSize, QKeySequence, QShortcut, QImage, QFont, QFontDatabase, QKeyEvent, QScreen, QPainterPath, QTransform
from PyQt6.QtPrintSupport import QPrinter
from PyQt6.QtCore import QThread
from payment_service import KSNETPayment

# [모듈 import]
# 같은 폴더에 camera_thread.py, photo_utils.py, widgets.py, constants.py 가 있어야 합니다.
from camera_thread import VideoThread
from photo_utils import merge_4cut_vertical, apply_filter, add_qr_to_image, FRAME_LAYOUTS
from widgets import ClickableLabel, BackArrowWidget, CircleButton, GradientButton, QRCheckWidget, GlobalTimerWidget, PaymentPopup
from constants import LAYOUT_OPTIONS_MASTER
from tether_service import capture_one_photo_blocking
from tether_worker import TetherCaptureManyThread

class PaymentApproveThread(QThread):
    finished = pyqtSignal(dict)

    def __init__(self, amount: int, parent=None):
        super().__init__(parent)
        self.amount = int(amount)

    def run(self):
        payment = KSNETPayment()  # 기본: http://localhost:27098
        result = payment.approve(amount=self.amount, installment=0, timeout=120)
        self.finished.emit(result)


class KioskMain(QMainWindow):

    def get_admin_shoot_count(self) -> int:
        n = int(self.admin_settings.get("total_shoot_count", 8))
        return max(1, min(12, n))

    
    def set_tether_status(self, msg: str):
        self.tether_status_text = msg
        print("[tether][ui]", msg)

    
    def __init__(self):
        from constants import DEFAULT_SHOOT_COUNT, MAX_SHOOT_COUNT

        super().__init__()

        # 🔥 폰트 로딩 (가장 먼저!)
        self.base_path = os.path.dirname(os.path.abspath(__file__))
        self.load_custom_fonts()       # 폰트 로드
        
        # 0. 디자인 기준 해상도 (16:9)
        self.DESIGN_W = 1920.0
        self.DESIGN_H = 1080.0

        # 현재 화면 추적용
        self.last_screen = None

        # 1. 기본 설정
        self.asset_root = os.path.join(self.base_path, "assets", "frames")
        self.click_count = 0 
        self.session_data = {}
        self.selected_indices = []
        self.captured_files = [] # 촬영된 파일 리스트 초기화
        self.is_mirrored = False  # 🔥 좌우반전 상태 추가
        
        # 관리자 설정
        self.admin_settings = {
            'print_qty': 1, 'shot_countdown': 3, 'total_shoot_count': 8,
            'mirror_mode': True, 'printer_name': 'Canon_E560_series',
            'use_qr': True, 
            'payment_mode': 1, # 0:무상, 1:유상, 2:코인
            'use_card': True, 'use_cash': True, 'use_coupon': True,
            'use_dark_mode': False,
            'price_full': 4000, 'price_half': 4000,
            'coin_price_per_sheet': 1,
            'print_count_min': 2, 'print_count_max': 12,
            'use_filter_page': True, 'save_raw_files': False,
            # 🔥 카메라 설정 추가
            'camera_index': 1,      # check_camera.py로 확인한 인덱스
            'camera_width': 1920,   # 해상도
            'camera_height': 1080,
            'camera_source': 'capture'  # 'capture' 또는 'tether'
        }

        self.event_config = self.load_event_config() 
        self.create_asset_folders()

        # 2. 윈도우 설정 (전체 배경 검은색 - 레터박스 역할)
        self.setWindowTitle("Photo Kiosk")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet("background-color: black;") 
        
        # 변수 초기화
        self.scale_factor = 1.0
        self.off_x = 0
        self.off_y = 0
        self.new_w = 1920
        self.new_h = 1080

        # 전체 화면 선적용
        self.showFullScreen()
        QApplication.processEvents()

        # 초기 화면 저장
        self.last_screen = self.screen()

        # 3. 메인 컨테이너 구성
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        
        # 실제 콘텐츠가 들어갈 16:9 컨테이너
        self.content_area = QWidget(self.central_widget)
        self.content_area.setStyleSheet("background-color: white;") 

        # 페이지 스택
        self.stack = QStackedWidget(self.content_area)
        
        self.init_ui()      
        self.update_ui_mode()
        
        self.cam_thread = None
        
        # 초기 리사이징 및 페이지 로드
        self.calculate_layout_geometry()
        self.show_page(0)

    def load_custom_fonts(self):
        """프로젝트 내 폰트 파일 로드"""
        font_dir = os.path.join(self.base_path, "assets", "fonts")
        
        if not os.path.exists(font_dir):
            print(f"⚠️ 폰트 폴더 없음: {font_dir}")
            return
        
        # 로드할 폰트 파일 목록
        font_files = [
            "Pretendard-Regular.otf",
            "Pretendard-Light.otf",
            "Pretendard-Medium.otf",
            "Pretendard-SemiBold.otf",
            "Pretendard-Bold.otf",
            "TikTokSans16pt-Regular.otf",
            "TikTokSans16pt-Light.otf",
            "TikTokSans16pt-Medium.otf",
            "TikTokSans16pt-SemiBold.otf",
            "TikTokSans16pt-Bold.otf"
        ]
        
        loaded_count = 0
        for font_file in font_files:
            font_path = os.path.join(font_dir, font_file)
            if os.path.exists(font_path):
                font_id = QFontDatabase.addApplicationFont(font_path)
                if font_id != -1:
                    font_families = QFontDatabase.applicationFontFamilies(font_id)
                    print(f"✅ 폰트 로드 성공: {font_families[0] if font_families else font_file}")
                    loaded_count += 1
                else:
                    print(f"❌ 폰트 로드 실패: {font_file}")
            else:
                print(f"⚠️ 폰트 파일 없음: {font_file}")
        
        print(f"\n총 {loaded_count}개 폰트 로드 완료\n")

        # 🔥 디버깅: 시스템에서 사용 가능한 모든 폰트 출력
        print("=" * 50)
        print("사용 가능한 폰트 패밀리:")
        all_families = QFontDatabase.families()
        for family in all_families:
            if 'Pretendard' in family or 'TikTok' in family:
                print(f"  - {family}")
        print("=" * 50)

    # -----------------------------------------------------------
    # [Config & Setup]
    # -----------------------------------------------------------
    def load_event_config(self):
        path = os.path.join(self.base_path, "event_config.json")
        if not os.path.exists(path):
            return {"event_name": "Default", "papers": {"full": {"v2": ["*"]}}}

        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[event_config] 로드 실패: {e} / path={path}")
            return {"event_name": "Default", "papers": {"full": {"v2": ["*"]}}}


    def create_asset_folders(self):
        for p, ls in LAYOUT_OPTIONS_MASTER.items():
            for k in ls.keys(): os.makedirs(os.path.join(self.asset_root, p, k), exist_ok=True)
        for m in ["white", "dark"]: os.makedirs(os.path.join(self.base_path, "assets", "backgrounds", m), exist_ok=True)
        os.makedirs(os.path.join(self.base_path, "assets", "fonts"), exist_ok=True)
        os.makedirs("data/original", exist_ok=True)
        os.makedirs("data/results", exist_ok=True)

    def update_ui_mode(self): pass

    # -----------------------------------------------------------
    # [Resize Logic] 16:9 비율 고정 + 레터박스
    # -----------------------------------------------------------
    def calculate_layout_geometry(self):
        # 현재 윈도우가 있는 화면 감지
        screen = self.screen()
        if screen is None:
            screen = QApplication.primaryScreen()
        
        rect = screen.geometry()
        self.screen_w = rect.width()
        self.screen_h = rect.height()

        # 화면 비율과 디자인 비율 비교
        screen_ratio = self.screen_w / self.screen_h
        design_ratio = self.DESIGN_W / self.DESIGN_H

        if screen_ratio > design_ratio:
            # 화면이 더 납작함 (좌우 여백)
            self.new_h = self.screen_h
            self.new_w = self.new_h * design_ratio
            self.scale_factor = self.new_h / self.DESIGN_H
            self.off_x = (self.screen_w - self.new_w) / 2
            self.off_y = 0
        else:
            # 화면이 더 좁음 (위아래 여백)
            self.new_w = self.screen_w
            self.new_h = self.new_w / design_ratio
            self.scale_factor = self.new_w / self.DESIGN_W
            self.off_x = 0
            self.off_y = (self.screen_h - self.new_h) / 2

        # 16:9 컨테이너 위치 및 크기 적용
        if hasattr(self, 'content_area'):
            self.content_area.setGeometry(
                int(self.off_x), 
                int(self.off_y), 
                int(self.new_w), 
                int(self.new_h)
            )
        
        # 스택 위젯도 16:9 컨테이너에 딱 맞게
        if hasattr(self, 'stack'):
            self.stack.setGeometry(0, 0, int(self.new_w), int(self.new_h))
            
            # 현재 페이지 위젯 강제 리사이징
            current_widget = self.stack.currentWidget()
            if current_widget:
                current_widget.setGeometry(0, 0, int(self.new_w), int(self.new_h))
                current_widget.resize(int(self.new_w), int(self.new_h))
                current_widget.updateGeometry()
                current_widget.update()

    def moveEvent(self, event):
        """윈도우가 다른 화면으로 이동할 때 자동 감지"""
        super().moveEvent(event)
        
        current_screen = self.screen()
        if current_screen and hasattr(self, 'last_screen'):
            if current_screen != self.last_screen:
                # 레이아웃 재계산
                self.calculate_layout_geometry()
                # 현재 페이지 리로드
                if hasattr(self, 'stack'):
                    self.reload_current_page(self.stack.currentIndex())
    
        if current_screen:
            self.last_screen = current_screen

    def resizeEvent(self, event):
        """윈도우 크기가 변경될 때"""
        super().resizeEvent(event)
        
        # 레이아웃 재계산
        self.calculate_layout_geometry()
        
        # 모든 페이지 강제 업데이트
        if hasattr(self, 'stack'):
            for i in range(self.stack.count()):
                widget = self.stack.widget(i)
                if widget:
                    widget.setGeometry(0, 0, int(self.new_w), int(self.new_h))
                    widget.resize(int(self.new_w), int(self.new_h))
                    widget.update()
            
            # 현재 페이지 리로드
            current_idx = self.stack.currentIndex()
            if current_idx >= 0:
                self.reload_current_page(current_idx)

    def reload_current_page(self, idx):
        if idx < 0: return
        # 페이지 리로드 로직
        if idx == 1: 
            old = self.stack.widget(1); self.page_frame = self.create_frame_page()
            self.stack.removeWidget(old); self.stack.insertWidget(1, self.page_frame); self.stack.setCurrentIndex(1); self.load_frame_options()
        elif idx == 2:
            old = self.stack.widget(2); self.page_payment = self.create_payment_page()
            self.stack.removeWidget(old); self.stack.insertWidget(2, self.page_payment); self.stack.setCurrentIndex(2); self.load_payment_page_logic()
        elif idx == 4:
            old = self.stack.widget(4); self.page_select = self.create_select_page()
            self.stack.removeWidget(old); # [수정] 오타 수정 (reifmoveWidget -> removeWidget)
            self.stack.insertWidget(4, self.page_select); self.stack.setCurrentIndex(4); self.load_select_page()
        elif idx == 5:
            old = self.stack.widget(5); self.page_filter = self.create_filter_page()
            self.stack.removeWidget(old); self.stack.insertWidget(5, self.page_filter); self.stack.setCurrentIndex(5); 
            if hasattr(self, 'final_print_path') and os.path.exists(self.final_print_path):
                self.result_label.setPixmap(QPixmap(self.final_print_path).scaled(800,1200, Qt.AspectRatioMode.KeepAspectRatio))
        elif idx == 6:
            old = self.stack.widget(6); self.page_print = self.create_printing_page()
            self.stack.removeWidget(old); self.stack.insertWidget(6, self.page_print); self.stack.setCurrentIndex(6)
        elif idx == 7: # Admin
            old = self.stack.widget(7); self.page_admin = self.create_admin_page()
            self.stack.removeWidget(old); self.stack.insertWidget(7, self.page_admin); self.stack.setCurrentIndex(7)

    # -----------------------------------------------------------
    # [Helper Methods] - 스케일링 함수 (ss
    # -----------------------------------------------------------
    def s(self, size):
        """ 1920x1080 기준 픽셀 값을 현재 비율에 맞춰 변환 """
        return int(size * self.scale_factor)
    
    def fs(self, size):
        """
        폰트 전용 스케일링 (Font Scale)
        
        윈도우 기준으로 최적화
        맥에서는 약간 크게 보이지만, 윈도우에서 정상 크기로 표시됨
        
        Args:
            size: 1920x1080 기준 폰트 크기 (pt)
        
        Returns:
            int: 스케일 적용 + OS 보정된 폰트 크기
        """
        scaled = size * self.scale_factor
        
        # 🔥 윈도우 기준 최적화
        # 맥에서는 약 12% 크게 보이지만, 윈도우에서 정상 크기
        if platform.system() == 'Darwin':  # macOS
            scaled *= 1.12
        
        return int(scaled)

    def create_header(self, parent_layout, title_text, sub_text="", show_back=True, back_callback=None):
        header_widget = QWidget()
        header_height = self.s(260)
        header_widget.setFixedHeight(header_height)
        header_widget.setStyleSheet("background: transparent;")
        
         # 🔥 타이틀/서브타이틀을 화면 전체 너비 기준 중앙 정렬
        title_box = QWidget(header_widget)
        title_box.setGeometry(0, 0, int(self.new_w), header_height)
        
        lbl_title = QLabel(title_text, title_box)
        lbl_title.setStyleSheet(f"font-family: 'TikTok Sans 16pt SemiBold'; font-size: {self.fs(40)}pt; color: black; background: transparent;")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_title.setGeometry(0, self.s(130), int(self.new_w), self.s(60))
        
        if sub_text:
            lbl_sub = QLabel(sub_text, title_box)
            lbl_sub.setStyleSheet(f"font-family: 'Pretendard SemiBold'; font-size: {self.fs(24)}pt; color: #555; background: transparent;")
            lbl_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_sub.setGeometry(0, self.s(130 + 60 + 13), int(self.new_w), self.s(40))

        if show_back and back_callback:
            btn_back = self.create_custom_back_btn(header_widget, back_callback)
            btn_back.move(self.s(110), self.s(117))
            btn_back.raise_()

        timer_box = QWidget(header_widget)
        timer_box.setFixedSize(self.s(200), self.s(140))
        timer_box.setStyleSheet(f"background-color: rgba(227, 227, 227, 0.8); border: {self.s(1)}px solid #5F5F5F; border-radius: {self.s(20)}px;")
        timer_box.move(int(self.new_w) - self.s(110) - self.s(200), self.s(117))
        timer_box.raise_()
        
        t_layout = QVBoxLayout(timer_box)
        t_layout.setContentsMargins(0, self.s(10), 0, self.s(10))
        t_layout.setSpacing(0)
        
        lbl_t = QLabel("TIMER")
        lbl_t.setStyleSheet(f"font-family: 'Pretendard SemiBold'; font-size: {self.fs(20)}pt; color: #828282; border: none; background: transparent;")
        lbl_t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        lbl_n = QLabel("")
        lbl_n.setStyleSheet(f"font-family: 'TikTok Sans 16pt SemiBold'; font-size: {self.fs(56)}pt; color: black; border: none; background: transparent;")
        lbl_n.setAlignment(Qt.AlignmentFlag.AlignCenter)

        t_layout.addWidget(lbl_t)
        t_layout.addWidget(lbl_n)

        parent_layout.addWidget(header_widget)
        return lbl_n

    def create_custom_back_btn(self, parent, callback):
        """뒤로가기 버튼"""
        btn = QPushButton(parent)
        btn.setFixedSize(self.s(140), self.s(140))
        btn.setStyleSheet(f"""
            QPushButton {{ background-color: #474747; border: {self.s(1)}px solid #787878; border-radius: {self.s(20)}px; }} 
            QPushButton:pressed {{ background-color: #333333; }}
        """)
        btn.clicked.connect(callback)
        
        arrow = BackArrowWidget(btn, color="#C2C2C2", thickness=self.s(4))
        arrow.setGeometry(self.s(26), self.s(48), self.s(24), self.s(44))
        
        lbl = QLabel("뒤로\n가기", btn)
        lbl.setGeometry(self.s(61), self.s(42), self.s(60), self.s(60))
        lbl.setStyleSheet(f"color: #C2C2C2; font-family: 'Pretendard SemiBold'; font-size: {self.fs(18)}pt; line-height: 120%; border: none; background: transparent;")
        
        return btn

    def apply_window_style(self, page_widget, bg_name="common"):
        """배경 이미지 적용"""
        m = "dark" if self.admin_settings.get("use_dark_mode") else "white"
        p = os.path.join(self.base_path, "assets", "backgrounds", m, f"{bg_name}.png")
        
        if os.path.exists(p):
            page_widget.bg_pixmap = QPixmap(p)
            def paint_bg(event):
                painter = QPainter(page_widget)
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                widget_width = page_widget.width()
                widget_height = page_widget.height()
                if widget_width <= 0 or widget_height <= 0:
                    widget_width = int(self.new_w)
                    widget_height = int(self.new_h)
                scaled_pixmap = page_widget.bg_pixmap.scaled(
                    widget_width, widget_height, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
                painter.drawPixmap(0, 0, scaled_pixmap)
            page_widget.paintEvent = paint_bg
            page_widget.update()
        else:
            page_widget.setStyleSheet("background-color: white;")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape: self.close()
        elif event.key() == Qt.Key.Key_A: self.show_page(99)

    def check_secret_code(self):
        self.click_count += 1
        if self.click_count >= 5: self.click_count = 0; self.show_page(99)

    # -----------------------------------------------------------
    # [UI Construction]
    # -----------------------------------------------------------
    def init_ui(self):
        self.page_start = self.create_start_page(); self.stack.addWidget(self.page_start)
        self.page_frame = self.create_frame_page(); self.stack.addWidget(self.page_frame)
        self.page_payment = self.create_payment_page(); self.stack.addWidget(self.page_payment)
        self.page_photo = self.create_photo_page(); self.stack.addWidget(self.page_photo)
        self.page_select = self.create_select_page(); self.stack.addWidget(self.page_select)  # 🔥 미리 생성
        self.page_filter = self.create_filter_page(); self.stack.addWidget(self.page_filter)
        self.page_print = self.create_printing_page(); self.stack.addWidget(self.page_print)
        self.page_admin = self.create_admin_page(); self.stack.addWidget(self.page_admin)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.process_timer_tick)

    # -----------------------------------------------------------
    # [Pages test]
    # -----------------------------------------------------------
    def create_start_page(self):
        page = QWidget(); self.apply_window_style(page, "intro")
        btn_bg = QToolButton(page)
        btn_bg.setGeometry(0, 0, int(self.new_w), int(self.new_h)) 
        btn_bg.setStyleSheet("background: transparent; border: none;")
        btn_bg.clicked.connect(lambda: self.show_page(1))
        adm = QPushButton(page)
        adm.setGeometry(0, 0, self.s(200), self.s(200))
        adm.setStyleSheet("background: transparent; border: none;")
        adm.clicked.connect(self.check_secret_code)
        return page

    def create_frame_page(self):
        page = QWidget()
        self.apply_window_style(page, "common")
        
        main_layout = QVBoxLayout(page)
        main_layout.setContentsMargins(0, 0, 0, self.s(60))
        main_layout.setSpacing(self.s(20))
        
        self.lbl_timer_frame = self.create_header(
            main_layout, 
            "Choose Your Frame", 
            "프레임 디자인을 선택해주세요", 
            True, 
            lambda: self.show_page(0)
        )
        
        # 🔥 컨테이너 (스크롤/일반 위젯을 담을 공간)
        scroll_container = QWidget()
        scroll_container.setStyleSheet("background: transparent;")
        container_layout = QHBoxLayout(scroll_container)
        container_layout.setContentsMargins(self.s(80), 0, self.s(80), 0)
        container_layout.setSpacing(0)
        
        # 🔥 스크롤 영역 생성 (나중에 조건부로 사용)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background: transparent; 
                border: none;
            }}
            QScrollArea > QWidget {{
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: {self.s(30)}px;
                margin: 0px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: qlineargradient(
                    spread:pad, x1:0, y1:1, x2:0, y2:0,
                    stop:0 #B6B6B6, stop:1 #F0F0F0
                );
                border: {self.s(1)}px solid #787878;
                border-radius: {self.s(15)}px;
                min-height: {self.s(40)}px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: qlineargradient(
                    spread:pad, x1:0, y1:1, x2:0, y2:0,
                    stop:0 #A0A0A0, stop:1 #E0E0E0
                );
            }}
            QScrollBar::handle:vertical:pressed {{
                background: qlineargradient(
                    spread:pad, x1:0, y1:1, x2:0, y2:0,
                    stop:0 #909090, stop:1 #D0D0D0
                );
            }}
            QScrollBar::add-line:vertical {{
                height: 0px;
                border: none;
                background: transparent;
            }}
            QScrollBar::sub-line:vertical {{
                height: 0px;
                border: none;
                background: transparent;
            }}
            QScrollBar::add-page:vertical {{
                background: transparent;
            }}
            QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
            QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {{
                background: transparent;
            }}
        """)
        
        # 🔥 일반 위젯 (스크롤 없이 사용)
        self.no_scroll_area = QWidget()
        self.no_scroll_area.setStyleSheet("background: transparent;")
        
        # 🔥 그리드 위젯 (공통)
        self.frame_grid_widget = QWidget()
        self.frame_grid_widget.setStyleSheet("background: transparent;")
        
        # 그리드 위젯을 감싸는 수평 레이아웃
        grid_wrapper_layout = QHBoxLayout(self.frame_grid_widget)
        grid_wrapper_layout.setContentsMargins(0, 0, 0, 0)
        grid_wrapper_layout.setSpacing(0)
        
        # 좌측 여백
        grid_wrapper_layout.addStretch(1)
        
        # 실제 그리드 컨테이너를 담을 수직 레이아웃
        grid_vertical_container = QWidget()
        grid_vertical_container.setStyleSheet("background: transparent;")
        self.grid_vertical_layout = QVBoxLayout(grid_vertical_container)
        self.grid_vertical_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_vertical_layout.setSpacing(0)
        
        # 상단 여백
        self.grid_top_stretch = self.grid_vertical_layout.addStretch(1)
        
        # 실제 그리드 컨테이너
        grid_inner_widget = QWidget()
        grid_inner_widget.setStyleSheet("background: transparent;")
        
        self.frame_grid = QGridLayout(grid_inner_widget)
        self.frame_grid.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignTop)
        self.frame_grid.setContentsMargins(0, 0, 0, self.s(50))
        self.frame_grid.setSpacing(self.s(30))
        
        self.grid_vertical_layout.addWidget(grid_inner_widget)
        
        # 하단 여백
        self.grid_bottom_stretch = self.grid_vertical_layout.addStretch(1)
        
        grid_wrapper_layout.addWidget(grid_vertical_container)
        
        # 우측 여백
        grid_wrapper_layout.addStretch(1)
        
        # 🔥 초기에는 일반 위젯 사용 (load_frame_options에서 전환)
        no_scroll_layout = QVBoxLayout(self.no_scroll_area)
        no_scroll_layout.setContentsMargins(0, 0, 0, 0)
        no_scroll_layout.addWidget(self.frame_grid_widget)
        
        container_layout.addWidget(self.no_scroll_area)
        
        # 🔥 컨테이너 레이아웃 참조 저장
        self.frame_container_layout = container_layout
        
        main_layout.addWidget(scroll_container)
        
        return page

    def create_payment_page(self):
        page = QWidget()
        self.apply_window_style(page, "common")
        
        main_layout = QVBoxLayout(page)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 1. 헤더 생성
        self.lbl_timer_payment = self.create_header(
            main_layout, "Payment", "수량을 선택해주세요", True, lambda: self.show_page(1)
        )
        
        # 2. 중앙 컨텐츠 영역
        content_area = QWidget()
        content_area.setStyleSheet("background: transparent; border: none;")
        self.content_v_layout = QVBoxLayout(content_area)
        
        # 수직 위치 설정 (모드별 80px 또는 160px 적용)
        mode = self.admin_settings.get("payment_mode", 1)
        top_margin = 160 if mode == 0 else 80
        self.content_v_layout.setContentsMargins(0, self.s(top_margin), 0, 0)
        
        # 🔥 수직/수평 모두 중앙 정렬 베이스로 설정
        self.content_v_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        # --- [결제 정보 그룹: 버튼+박스+체크박스 전체 덩어리] ---
        payment_group_widget = QWidget()
        # 그룹의 전체 너비를 조절 버튼과 박스들이 포함된 너비로 고정 (약 1000px)
        # 마이너스(140) + 간격(50) + 박스(500) + 간격(50) + 플러스(140) = 880px
        payment_group_widget.setFixedWidth(self.s(880)) 
        payment_group_layout = QVBoxLayout(payment_group_widget)
        payment_group_layout.setContentsMargins(0, 0, 0, 0)
        payment_group_layout.setSpacing(0)
        # 그룹 내부 요소들을 왼쪽 정렬하여 기준선을 맞춤
        payment_group_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # 2-1. 수량 조절 행 (-, 박스, +)
        controls_widget = QWidget()
        controls_layout = QHBoxLayout(controls_widget)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(0)
        controls_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # [A] 마이너스 버튼
        self.btn_minus = CircleButton(page, False, self.s)
        self.btn_minus.clicked.connect(lambda: self.update_print_qty(-1))

        # [B] 중앙 박스 스택
        display_stack_widget = QWidget()
        display_stack_layout = QVBoxLayout(display_stack_widget)
        display_stack_layout.setContentsMargins(self.s(50), 0, self.s(50), 0)
        display_stack_layout.setSpacing(self.s(20))
        
        # 수량창/금액창
        for attr, text in [('lbl_qty', "2장"), ('lbl_price', "4,000원")]:
            lbl = QLabel(text)
            lbl.setFixedSize(self.s(500), self.s(140))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"background-color: #E3E3E3; border: none; border-radius: {self.s(20)}px; font-family: 'Pretendard SemiBold'; font-size: {self.fs(56)}px; color: black;")
            display_stack_layout.addWidget(lbl)
            if attr == 'lbl_qty': self.c_qty = self.lbl_qty = lbl
            else: self.c_prc = self.lbl_price = lbl

        # [C] 플러스 버튼
        self.btn_plus = CircleButton(page, True, self.s)
        self.btn_plus.clicked.connect(lambda: self.update_print_qty(1))

        controls_layout.addWidget(self.btn_minus)
        controls_layout.addWidget(display_stack_widget)
        controls_layout.addWidget(self.btn_plus)

        # 2-2. QR 체크박스 영역 (박스 왼쪽 라인에 맞춤)
        qr_container = QWidget()
        qr_layout = QHBoxLayout(qr_container)
        # 마이너스 버튼(140) + 간격(50) = 190px 만큼 띄워서 박스 시작점에 맞춤
        qr_layout.setContentsMargins(self.s(190), self.s(50), 0, 0)
        qr_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.chk_qr = QRCheckWidget(page, self.s)
        qr_layout.addWidget(self.chk_qr)

        # 그룹에 행들 추가
        payment_group_layout.addWidget(controls_widget)
        payment_group_layout.addWidget(qr_container)

        # 🔥 전체 레이아웃에 그룹 위젯을 추가 (자동으로 가운데 정렬됨)
        self.content_v_layout.addWidget(payment_group_widget)
        
        main_layout.addWidget(content_area, 1)

        # 3. 하단 결제 버튼 영역 (기존 코드 동일)
        self.btn_widget = QWidget(page)
        self.btn_widget.setStyleSheet("background: transparent; border: none;")
        self.btn_widget.setFixedHeight(self.s(140))
        button_y = int(self.new_h) - self.s(120) - self.s(140)
        self.btn_widget.setGeometry(0, button_y, int(self.new_w), self.s(140))
        self.payment_btn_layout = QHBoxLayout(self.btn_widget)
        self.payment_btn_layout.setSpacing(self.s(30))
        self.payment_btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.payment_btn_layout.setContentsMargins(0, 0, 0, 0)
        
        return page
    
    def create_coupon_ui(self):
        self.btn_close_cp = QPushButton("X", self.coupon_widget)
        self.btn_close_cp.setGeometry(self.s(340), self.s(10), self.s(50), self.s(50))
        self.btn_close_cp.clicked.connect(self.coupon_widget.hide)
        self.btn_close_cp.setStyleSheet(f"font-size: {self.fs(24)}px; font-weight: bold; background: transparent; color: #999; border: none;")
        cl = QVBoxLayout(self.coupon_widget); cl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.input_coupon = QLineEdit(); self.input_coupon.setFixedSize(self.s(400), self.s(80)); self.input_coupon.setAlignment(Qt.AlignmentFlag.AlignCenter); self.input_coupon.setStyleSheet(f"font-size: {self.fs(30)}px; border-radius: {self.s(10)}px; border: 2px solid #ccc;")
        cl.addWidget(self.input_coupon)
        kp = QWidget(); kl = QGridLayout(kp); kl.setSpacing(self.s(10))
        for i, k in enumerate(['1','2','3','4','5','6','7','8','9','C','0','OK']):
            b = QPushButton(k); b.setFixedSize(self.s(80), self.s(80))
            b.setStyleSheet(f"font-size: {self.fs(30)}px; font-weight: bold; border-radius: {self.s(10)}px; background-color: {'#ffccdd' if k=='OK' else 'white'}; border: 1px solid #999;")
            if k=='OK': b.clicked.connect(self.process_coupon_ok)
            elif k=='C': b.clicked.connect(self.input_coupon.clear)
            else: b.clicked.connect(lambda _, x=k: self.input_coupon.setText(self.input_coupon.text()+x))
            kl.addWidget(b, i//3, i%3)
        cl.addWidget(kp)

    def process_coupon_ok(self):
        self.show_payment_popup("coupon")

    def create_photo_page(self):
        page = QWidget()
        self.apply_window_style(page, "white")
        
        main_layout = QVBoxLayout(page)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 헤더 (기존 코드 동일)
        self.header_widget = QWidget()
        self.header_widget.setFixedHeight(self.s(130))
        self.header_widget.setStyleSheet("""
            QWidget {
                background: qlineargradient(
                    spread:pad, x1:0, y1:1, x2:0, y2:0,
                    stop:0 #B6B6B6, stop:1 #F0F0F0
                );
            }
        """)
        
        self.lbl_timer_header = QLabel("")
        self.lbl_timer_header.setParent(self.header_widget)
        self.lbl_timer_header.setGeometry(0, 0, int(self.new_w), self.s(130))
        self.lbl_timer_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_timer_header.setStyleSheet(f"""
            font-family: 'TikTok Sans 16pt SemiBold';
            font-size: {self.fs(56)}pt;
            color: black;
            background: transparent;
        """)
        
        self.lbl_shot_count = QLabel("1/8")
        self.lbl_shot_count.setParent(self.header_widget)
        shot_count_width = self.s(200)
        self.lbl_shot_count.setGeometry(
            int(self.new_w) - self.s(88) - shot_count_width,
            0,
            shot_count_width,
            self.s(130)
        )
        self.lbl_shot_count.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_shot_count.setStyleSheet(f"""
            font-family: 'TikTok Sans 16pt SemiBold';
            font-size: {self.fs(40)}pt;
            color: #313131;
            background: transparent;
        """)
        
        main_layout.addWidget(self.header_widget)
        
        # 카메라 영역
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        side_w = self.s(230)
        
        # 🔥 좌측 사이드바 (여백 30px)
        self.left_sidebar = QWidget()
        self.left_sidebar.setFixedWidth(side_w)
        self.left_sidebar.setStyleSheet("background-color: #1E1E1E;")
        self.left_layout = QVBoxLayout(self.left_sidebar)
        self.left_layout.setContentsMargins(self.s(30), self.s(30), self.s(30), self.s(30))
        self.left_layout.setSpacing(self.s(15))  # 미리보기 간격
        self.left_previews = []
        
        # 중앙 비디오
        self.video_container = QWidget()
        self.video_container.setStyleSheet("background: black;")
        self.video_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        v_layout = QVBoxLayout(self.video_container)
        v_layout.setContentsMargins(0, 0, 0, 0)
        self.video_label = QLabel("Camera Loading...")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v_layout.addWidget(self.video_label)
        
        # 🔥 우측 사이드바 (여백 30px)
        self.right_sidebar = QWidget()
        self.right_sidebar.setFixedWidth(side_w)
        self.right_sidebar.setStyleSheet("background-color: #1E1E1E;")
        self.right_layout = QVBoxLayout(self.right_sidebar)
        self.right_layout.setContentsMargins(self.s(30), self.s(30), self.s(30), self.s(30))
        self.right_layout.setSpacing(self.s(15))  # 미리보기 간격
        self.right_previews = []
        
        content_layout.addWidget(self.left_sidebar)
        content_layout.addWidget(self.video_container, stretch=1)
        content_layout.addWidget(self.right_sidebar)
        
        main_layout.addLayout(content_layout)
        
        return page

    def create_select_page(self):
        page = QWidget()
        self.apply_window_style(page, "common")
        
        main_layout = QVBoxLayout(page)
        main_layout.setContentsMargins(0, 0, 0, self.s(50))
        main_layout.setSpacing(self.s(20))
        
        # 헤더
        target_count = self.session_data.get('target_count', 4)
        self.lbl_timer_select = self.create_header(
            main_layout,
            "Select Your Picture",
            f"총 {target_count}컷의 사진을 선택해주세요",
            False,
            None
        )
        
        # 메인 컨텐츠 영역
        content_widget = QWidget()
        content_widget.setStyleSheet("background: transparent;")
        
        preview_bg_y = self.s(10) 

        # 좌측: 프레임 미리보기 배경
        preview_bg = QWidget(content_widget)
        preview_bg.setFixedSize(self.s(700), self.s(700))
        preview_bg.setStyleSheet(f"""
            background-color: #ECECEC;
            border-radius: {self.s(12)}px;
        """)
        preview_bg.move(self.s(110), preview_bg_y) 
        
        # 미리보기 라벨
        self.lbl_select_preview = ClickableLabel(preview_bg)
        self.lbl_select_preview.setGeometry(self.s(50), self.s(50), self.s(600), self.s(600))
        self.lbl_select_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_select_preview.setStyleSheet("background: transparent; border: none;")
        self.lbl_select_preview.setScaledContents(False)
        self.lbl_select_preview.clicked.connect(self.on_preview_clicked)
        
       # 🔥 프레임 구멍 비율에 따라 그리드 배치 결정
        paper = self.session_data.get('paper_type', 'full')
        layout = self.session_data.get('layout_key', 'v2')
        key = f"{paper}_{layout}"

        print(f"[DEBUG] 그리드 생성 - paper: {paper}, layout: {layout}, key: {key}")

        layout_list = FRAME_LAYOUTS.get(key, [])

        # 구멍 비율 계산
        if layout_list:
            first_slot = layout_list[0]
            hole_w = first_slot['w']
            hole_h = first_slot['h']
            hole_ratio = hole_w / hole_h
            print(f"[DEBUG] 첫 번째 구멍: {hole_w}x{hole_h}, 비율: {hole_ratio:.3f}")
        else:
            hole_ratio = 1.0
            print(f"[DEBUG] 레이아웃 데이터 없음, 기본 비율 사용: {hole_ratio}")

        # 비율에 따라 행/열 결정
        if hole_ratio > 1.1:
            # 가로형 (가로가 더 넓음)
            grid_cols = 4
            grid_rows = 3
            print(f"[DEBUG] 가로형 그리드 선택: 4열 x 3행 (비율 {hole_ratio:.3f} > 1.1)")
        elif hole_ratio < 0.9:
            # 세로형 (세로가 더 김)
            grid_cols = 6
            grid_rows = 2
            print(f"[DEBUG] 세로형 그리드 선택: 6열 x 2행 (비율 {hole_ratio:.3f} < 0.9)")
        else:
            # 정방형 (비슷한 비율)
            grid_cols = 5
            grid_rows = 3
            print(f"[DEBUG] 정방형 그리드 선택: 5열 x 3행 (0.9 ≤ {hole_ratio:.3f} ≤ 1.1)")

        # 우측: 촬영 사진 그리드
        grid_container = QWidget(content_widget)
        grid_container.setStyleSheet("background: transparent;")

        # 그리드 영역 계산
        grid_x = self.s(110 + 700 + 30)
        grid_right = int(self.new_w) - self.s(110)
        grid_width = grid_right - grid_x
        grid_y = self.s(30)
        grid_bottom = self.s(30 + 700 - 140 - 30)
        grid_height = grid_bottom - grid_y

        print(f"[DEBUG] 그리드 영역: x={grid_x}, y={grid_y}, w={grid_width}, h={grid_height}")

        # 그리드 컨테이너 배치
        grid_container.setGeometry(grid_x, grid_y, grid_width, grid_height)

        # QGridLayout을 직접 grid_container에 설정
        self.photo_grid = QGridLayout(grid_container)
        self.photo_grid.setSpacing(0)  # 🔥 간격 0
        self.photo_grid.setContentsMargins(0, 0, 0, 0)  # 🔥 여백 0

        # 🔥 각 버튼의 크기 계산 (구멍 비율 유지)
        btn_width = grid_width // grid_cols
        btn_height = grid_height // grid_rows

        # 구멍 비율에 맞춰 조정
        height_from_width = int(btn_width / hole_ratio)
        width_from_height = int(btn_height * hole_ratio)

        if height_from_width <= btn_height:
            # 너비 기준
            final_btn_width = btn_width
            final_btn_height = height_from_width
        else:
            # 높이 기준
            final_btn_width = width_from_height
            final_btn_height = btn_height

        print(f"[DEBUG] 버튼 크기: {final_btn_width}x{final_btn_height} (비율 {hole_ratio:.3f})")

        self.photo_buttons = []

        # 동적으로 12개 버튼 배치
        for i in range(12):
            b = QPushButton()
            b.setStyleSheet(f"""
                QPushButton {{
                    border: none;
                    background-color: white;
                    padding: 0px;
                    margin: 0px;
                }}
                QPushButton:hover {{
                    background-color: #f5f5f5;
                }}
                QPushButton:pressed {{
                    background-color: #e0e0e0;
                }}
            """)
            
            # 🔥 고정 크기 설정 (구멍 비율 유지)
            b.setFixedSize(final_btn_width, final_btn_height)
            
            b.clicked.connect(lambda checked=False, x=i: self.on_source_click(x))
            self.photo_buttons.append(b)
            
            # 행/열 계산
            row = i // grid_cols
            col = i % grid_cols
            
            # 🔥 중앙 정렬로 추가
            self.photo_grid.addWidget(b, row, col, Qt.AlignmentFlag.AlignCenter)
        
        # 선택 완료 버튼
        self.btn_finish_select = GradientButton("선택 완료", "Complete", content_widget, self.s)
        btn_x = int(self.new_w) - self.s(110) - self.s(350)
        btn_y = preview_bg_y + self.s(700 - 140)  # 🔥 preview_bg_y 기준으로 계산
        self.btn_finish_select.move(btn_x, btn_y)
        self.btn_finish_select.setEnabled(False)
        self.btn_finish_select.clicked.connect(self.confirm_selection)
        
        content_widget.setGeometry(0, 0, int(self.new_w), int(self.new_h))
        
        main_layout.addWidget(content_widget)
        
        return page

    def on_source_click(self, i):
        """사진 그리드 클릭 처리 (중복 선택 가능)"""
        # 🔥 선택 가능한 빈 슬롯이 있는지 확인
        if None not in self.selected_indices:
            # 모든 슬롯이 차있으면 무시
            return
        
        # 🔥 첫 번째 빈 슬롯에 추가
        idx = self.selected_indices.index(None)
        self.selected_indices[idx] = i
        self.load_select_page()

    def on_preview_clicked(self, x, y):
        """미리보기 클릭 시 해당 슬롯 제거"""
        w = self.lbl_select_preview.width()
        h = self.lbl_select_preview.height()
        
        if w <= 0 or h <= 0:
            return
        
        k = f"{self.session_data.get('paper_type','full')}_{self.session_data.get('layout_key','v2')}"
        ld = FRAME_LAYOUTS.get(k, [])
        
        if not ld:
            return
        
        sx = w / 2400
        sy = h / 3600
        
        for i, cd in enumerate(ld):
            cx, cy, cw, ch = int(cd['x']*sx), int(cd['y']*sy), int(cd['w']*sx), int(cd['h']*sy)
            if cx <= x <= cx + cw and cy <= y <= cy + ch:
                # 🔥 안전한 인덱스 접근
                if i < len(self.selected_indices):
                    self.selected_indices[i] = None
                    self.load_select_page()
                break

    def load_select_page(self):
        t = self.session_data.get('target_count', 4)
        if len(self.selected_indices) != t:
            self.selected_indices = [None] * t
        
        sp = [self.captured_files[i] if i is not None and i < len(self.captured_files) else None for i in self.selected_indices]
        self.draw_select_preview(sp)
        
        # 중복 선택 카운트
        selection_count = {}
        for idx in self.selected_indices:
            if idx is not None:
                selection_count[idx] = selection_count.get(idx, 0) + 1
        
        # 프레임 레이아웃 정보 가져오기
        paper = self.session_data.get('paper_type', 'full')
        layout = self.session_data.get('layout_key', 'v2')
        key = f"{paper}_{layout}"
        layout_list = FRAME_LAYOUTS.get(key, [])
        
        # 구멍 비율 계산
        if layout_list:
            first_slot = layout_list[0]
            hole_ratio = first_slot['w'] / first_slot['h']
        else:
            hole_ratio = 3 / 4
        
        for i, b in enumerate(self.photo_buttons):
            if i < len(self.captured_files):
                original_pix = QPixmap(self.captured_files[i])
                
                if original_pix.isNull():
                    b.setIcon(QIcon())
                    b.setEnabled(False)
                    continue
                
                # 구멍 비율에 맞춰 이미지 크롭
                img_w = original_pix.width()
                img_h = original_pix.height()
                img_ratio = img_w / img_h
                
                if img_ratio > hole_ratio:
                    crop_h = img_h
                    crop_w = int(crop_h * hole_ratio)
                    crop_x = (img_w - crop_w) // 2
                    crop_y = 0
                else:
                    crop_w = img_w
                    crop_h = int(crop_w / hole_ratio)
                    crop_x = 0
                    crop_y = (img_h - crop_h) // 2
                
                cropped_pix = original_pix.copy(crop_x, crop_y, crop_w, crop_h)
                
                # 선택 횟수 오버레이
                if i in selection_count:
                    count = selection_count[i]
                    pt = QPainter(cropped_pix)
                    pt.fillRect(cropped_pix.rect(), QColor(0, 0, 0, 100))
                    pt.setPen(QPen(Qt.GlobalColor.green, self.s(40)))
                    pt.setFont(QFont("Arial", self.fs(100), QFont.Weight.Bold))
                    pt.drawText(cropped_pix.rect(), Qt.AlignmentFlag.AlignCenter, str(count))
                    pt.end()
                
                b.setIcon(QIcon(cropped_pix))
                b.setIconSize(QSize(self.s(250), self.s(250)))
                b.setEnabled(True)
            else:
                b.setIcon(QIcon())
                b.setEnabled(False)
        
        is_complete = all(x is not None for x in self.selected_indices)
        self.btn_finish_select.setEnabled(is_complete)

    def draw_select_preview(self, photo_paths):
        try:
            # 프레임 정보 가져오기
            paper_type = self.session_data.get('paper_type', 'full')
            layout_key = self.session_data.get('layout_key', 'v2')
            k = f"{paper_type}_{layout_key}"
            ld = FRAME_LAYOUTS.get(k, [])
            
            if not ld:
                print(f"[ERROR] 레이아웃 데이터 없음: {k}")
                return
            
            # 🔥 프레임 원본 크기 및 방향 판단
            # 레이아웃 키로 가로/세로 판단
            if layout_key.startswith('h'):
                # 가로형: 3600x2400
                canvas_w, canvas_h = 3600, 2400
                print(f"[DEBUG] 가로형 프레임 - 3600x2400")
            else:
                # 세로형: 2400x3600
                canvas_w, canvas_h = 2400, 3600
                print(f"[DEBUG] 세로형 프레임 - 2400x3600")
            
            frame_ratio = canvas_w / canvas_h
            
            # 라벨 크기
            label_w = self.lbl_select_preview.width()
            label_h = self.lbl_select_preview.height()
            
            if label_w <= 0 or label_h <= 0:
                label_w, label_h = self.s(600), self.s(600)
            
            # 🔥 프레임 비율에 맞춰 그릴 크기 계산
            label_ratio = label_w / label_h
            
            if label_ratio > frame_ratio:
                # 라벨이 더 넓음 -> 높이 기준
                draw_h = label_h
                draw_w = int(draw_h * frame_ratio)
            else:
                # 라벨이 더 좁음 -> 너비 기준
                draw_w = label_w
                draw_h = int(draw_w / frame_ratio)
            
            if draw_w <= 0 or draw_h <= 0:
                print("[ERROR] 잘못된 미리보기 크기")
                return
            
            print(f"[DEBUG] 그릴 크기: {draw_w}x{draw_h}, 비율: {frame_ratio:.3f}")
            
            # 🔥 캔버스 생성
            pm = QPixmap(draw_w, draw_h)
            pm.fill(Qt.GlobalColor.white)
            
            pt = QPainter(pm)
            pt.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            fp = self.session_data.get('frame_path')
            
            # 🔥 스케일 비율
            sx = draw_w / canvas_w
            sy = draw_h / canvas_h
            
            # 사진 배치
            for i, cd in enumerate(ld):
                x, y, cw, ch = int(cd['x']*sx), int(cd['y']*sy), int(cd['w']*sx), int(cd['h']*sy)
                
                if photo_paths and i < len(photo_paths) and photo_paths[i]:
                    if not os.path.exists(photo_paths[i]):
                        pt.fillRect(x, y, cw, ch, QColor(220, 220, 220))
                        continue
                    
                    img = QPixmap(photo_paths[i])
                    if img.isNull():
                        pt.fillRect(x, y, cw, ch, QColor(220, 220, 220))
                        continue
                        
                    img = img.scaled(
                        cw, ch, 
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding, 
                        Qt.TransformationMode.SmoothTransformation
                    )
                    crop_x = (img.width() - cw) // 2
                    crop_y = (img.height() - ch) // 2
                    pt.drawPixmap(x, y, cw, ch, img, crop_x, crop_y, cw, ch)
                else:
                    pt.fillRect(x, y, cw, ch, QColor(220, 220, 220))
            
            # 프레임 오버레이
            if fp and os.path.exists(fp):
                frame_scaled = QPixmap(fp).scaled(
                    draw_w, draw_h, 
                    Qt.AspectRatioMode.IgnoreAspectRatio, 
                    Qt.TransformationMode.SmoothTransformation
                )
                if not frame_scaled.isNull():
                    pt.drawPixmap(0, 0, frame_scaled)
            
            pt.end()
            
            # 라벨에 표시
            self.lbl_select_preview.setPixmap(pm)
            
        except Exception as e:
            print(f"[ERROR] draw_select_preview 오류: {e}")
            import traceback
            traceback.print_exc()

    def create_filter_page(self):
        page = QWidget()
        self.apply_window_style(page, "common")
        
        main_layout = QVBoxLayout(page)
        main_layout.setContentsMargins(0, 0, 0, self.s(50))
        main_layout.setSpacing(self.s(20))
        
        # 헤더
        self.lbl_timer_filter = self.create_header(
            main_layout,
            "Select your Filter",
            "필터를 선택해주세요",
            False,
            None
        )
        
        # 메인 컨텐츠 영역
        content_widget = QWidget()
        content_widget.setStyleSheet("background: transparent;")

        # 🔥 통일된 상단 y 위치
        top_y = self.s(10)

        # 좌측: 프레임 미리보기 배경
        preview_bg = QWidget(content_widget)
        preview_bg.setFixedSize(self.s(700), self.s(700))
        preview_bg.setStyleSheet(f"""
            background-color: #ECECEC;
            border-radius: {self.s(12)}px;
        """)
        preview_bg.move(self.s(110), top_y)
        
        # 미리보기 라벨
        self.result_label = QLabel(preview_bg)
        self.result_label.setGeometry(self.s(50), self.s(50), self.s(600), self.s(600))
        self.result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_label.setStyleSheet("background: transparent; border: none;")
        self.result_label.setScaledContents(False)
        
        # 🔥 우측 영역 시작 위치 (상단 통일)
        right_x = self.s(110 + 700 + 30)
        
        # 🔥 출력하기 버튼 위치 (사진선택완료와 동일)
        btn_x = int(self.new_w) - self.s(110) - self.s(350)
        btn_y = top_y + self.s(700 - 140)
        
        # 🔥 필터/좌우반전 배경 높이 = 출력하기 버튼 상단 30px까지
        filter_bg_height = btn_y - top_y - self.s(30)
        
        # 🔥 필터 선택 배경 너비
        filter_content_width = self.s(40 + 140 + 20 + 140 + 20 + 140 + 40)  # 540px
        
        # 필터 선택 배경
        filter_bg = QWidget(content_widget)
        filter_bg.setGeometry(right_x, top_y, filter_content_width, filter_bg_height)  # 🔥 top_y 사용
        filter_bg.setStyleSheet(f"""
            background-color: rgba(236, 236, 236, 0.5);
            border-radius: {self.s(20)}px;
        """)
        
        # '필터' 텍스트
        lbl_filter_title = QLabel("필터", filter_bg)
        lbl_filter_title.setGeometry(self.s(40), self.s(40), self.s(200), self.s(28))
        lbl_filter_title.setStyleSheet(f"""
            font-family: 'Pretendard SemiBold';
            font-size: {self.fs(28)}pt;
            color: rgba(0, 0, 0, 0.5);
            background: transparent;
        """)
        
        # 필터 버튼 그리드 (하단 정렬)
        filter_buttons_y = filter_bg_height - self.s(40 + 140 + 20 + 140)
        
        filter_grid_widget = QWidget(filter_bg)
        filter_grid_widget.setGeometry(
            self.s(40), 
            int(filter_buttons_y),
            self.s(140*3 + 20*2), 
            self.s(140*2 + 20)
        )
        filter_grid = QGridLayout(filter_grid_widget)
        filter_grid.setContentsMargins(0, 0, 0, 0)
        filter_grid.setSpacing(self.s(20))
        
        # 필터 버튼들
        fs = [
            ("원본", "original"), 
            ("웜톤", "warm"), 
            ("쿨톤", "cool"), 
            ("밝게", "bright"),
            ("어둡게", "dark"),
            ("뽀샤시", "beauty")
        ]
        
        self.filter_buttons = []
        for idx, (t, m) in enumerate(fs):
            b = QPushButton(t)
            b.setFixedSize(self.s(140), self.s(140))
            b.setCheckable(True)
            if m == "original":
                b.setChecked(True)
            
            b.setStyleSheet(f"""
                QPushButton {{ 
                    background-color: #474747;
                    color: rgba(255, 255, 255, 0.5);
                    font-family: 'Pretendard SemiBold';
                    font-size: {self.fs(28)}pt;
                    border-radius: {self.s(20)}px;
                    border: none;
                }} 
                QPushButton:checked {{ 
                    background-color: #9C77FF;
                    color: rgba(255, 255, 255, 1.0);
                }}
                QPushButton:hover {{ 
                    background-color: #5a5a5a;
                }}
            """)
            b.clicked.connect(lambda _, x=m, btn=b: self.apply_filter_click(x, btn))
            
            row = idx // 3
            col = idx % 3
            filter_grid.addWidget(b, row, col)
            self.filter_buttons.append(b)
        
        # 🔥 좌우반전 배경 (필터 배경 우측, 상단 정렬)
        mirror_bg_x = right_x + filter_content_width + self.s(30)
        mirror_bg_width = int(self.new_w) - mirror_bg_x - self.s(110)
        
        mirror_bg = QWidget(content_widget)
        mirror_bg.setGeometry(mirror_bg_x, top_y, mirror_bg_width, filter_bg_height)  # 🔥 top_y 사용
        mirror_bg.setStyleSheet(f"""
            background-color: rgba(236, 236, 236, 0.5);
            border-radius: {self.s(20)}px;
        """)
        
        # '좌우반전' 텍스트
        lbl_mirror_title = QLabel("좌우반전", mirror_bg)
        lbl_mirror_title.setGeometry(self.s(40), self.s(40), self.s(200), self.s(28))
        lbl_mirror_title.setStyleSheet(f"""
            font-family: 'Pretendard SemiBold';
            font-size: {self.fs(28)}pt;
            color: rgba(0, 0, 0, 0.5);
            background: transparent;
        """)
        
        # ON/OFF 버튼 (필터 버튼과 같은 높이)
        mirror_btn_y = int(filter_buttons_y)
        
        # ON 버튼
        self.btn_mirror_on = QPushButton("ON", mirror_bg)
        self.btn_mirror_on.setGeometry(self.s(40), mirror_btn_y, self.s(140), self.s(140))
        self.btn_mirror_on.setCheckable(True)
        self.btn_mirror_on.setChecked(True)
        self.btn_mirror_on.setStyleSheet(f"""
            QPushButton {{ 
                background-color: #474747;
                color: rgba(255, 255, 255, 0.5);
                font-family: 'Pretendard SemiBold';
                font-size: {self.fs(28)}pt;
                border-radius: {self.s(20)}px;
                border: none;
            }} 
            QPushButton:checked {{ 
                background-color: #9C77FF;
                color: rgba(255, 255, 255, 1.0);
            }}
            QPushButton:hover {{ 
                background-color: #5a5a5a;
            }}
        """)
        self.btn_mirror_on.clicked.connect(lambda: self.toggle_mirror(True))
        
        # OFF 버튼
        self.btn_mirror_off = QPushButton("OFF", mirror_bg)
        self.btn_mirror_off.setGeometry(self.s(40 + 140 + 20), mirror_btn_y, self.s(140), self.s(140))
        self.btn_mirror_off.setCheckable(True)
        self.btn_mirror_off.setStyleSheet(f"""
            QPushButton {{ 
                background-color: #474747;
                color: rgba(255, 255, 255, 0.5);
                font-family: 'Pretendard SemiBold';
                font-size: {self.fs(28)}pt;
                border-radius: {self.s(20)}px;
                border: none;
            }} 
            QPushButton:checked {{ 
                background-color: #9C77FF;
                color: rgba(255, 255, 255, 1.0);
            }}
            QPushButton:hover {{ 
                background-color: #5a5a5a;
            }}
        """)
        self.btn_mirror_off.clicked.connect(lambda: self.toggle_mirror(False))
        
        # 🔥 출력하기 버튼 (사진선택완료와 동일한 위치)
        self.btn_print = GradientButton("출력하기", "Print", content_widget, self.s)
        self.btn_print.move(btn_x, btn_y)
        self.btn_print.clicked.connect(self.start_printing)
        
        content_widget.setGeometry(0, 0, int(self.new_w), int(self.new_h))
        
        main_layout.addWidget(content_widget)
        
        return page

    def toggle_mirror(self, is_on):
        """좌우반전 토글 - ON/OFF 버튼 방식"""
        # 버튼 상태 업데이트
        if is_on:
            self.btn_mirror_on.setChecked(True)
            self.btn_mirror_off.setChecked(False)
        else:
            self.btn_mirror_on.setChecked(False)
            self.btn_mirror_off.setChecked(True)
        
        self.is_mirrored = is_on
        
        # 원본 사진들을 좌우반전한 후 프레임 합성
        sp = [self.captured_files[i] for i in self.selected_indices if i is not None]
        fp = self.session_data.get('frame_path')
        l_key = self.session_data.get('layout_key')
        fk = f"{self.session_data['paper_type']}_{l_key}"
        
        # 좌우반전된 사진들 생성
        if self.is_mirrored:
            mirrored_photos = []
            for photo_path in sp:
                img = QPixmap(photo_path)
                img = img.toImage().mirrored(True, False)
                img = QPixmap.fromImage(img)
                temp_path = photo_path.replace('.jpg', '_temp_mirror.jpg')
                img.save(temp_path)
                mirrored_photos.append(temp_path)
            merged_path = merge_4cut_vertical(mirrored_photos, fp, fk)
        else:
            merged_path = merge_4cut_vertical(sp, fp, fk)
        
        # 현재 필터 적용
        if hasattr(self, 'current_filter_mode'):
            self.final_print_path = apply_filter(merged_path, self.current_filter_mode)
        else:
            self.final_print_path = merged_path
        
        # 미리보기 업데이트
        self.result_label.setPixmap(QPixmap(self.final_print_path).scaled(
            self.s(600), self.s(600),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ))

    def apply_filter_click(self, m, clicked_btn):
        """필터 적용 - 버튼 상태 업데이트"""
        # 🔥 모든 필터 버튼 체크 해제 후 클릭된 버튼만 체크
        for btn in self.filter_buttons:
            btn.setChecked(False)
        clicked_btn.setChecked(True)
        
        self.current_filter_mode = m
        
        # 좌우반전 상태에 따라 원본 이미지 선택
        sp = [self.captured_files[i] for i in self.selected_indices if i is not None]
        fp = self.session_data.get('frame_path')
        l_key = self.session_data.get('layout_key')
        fk = f"{self.session_data['paper_type']}_{l_key}"
        
        # 좌우반전이 활성화되어 있으면
        if self.is_mirrored:
            mirrored_photos = []
            for photo_path in sp:
                img = QPixmap(photo_path)
                img = img.toImage().mirrored(True, False)
                img = QPixmap.fromImage(img)
                temp_path = photo_path.replace('.jpg', '_temp_mirror.jpg')
                img.save(temp_path)
                mirrored_photos.append(temp_path)
            merged_path = merge_4cut_vertical(mirrored_photos, fp, fk)
        else:
            merged_path = merge_4cut_vertical(sp, fp, fk)
        
        # 필터 적용
        self.final_print_path = apply_filter(merged_path, m)
        
        # 미리보기 업데이트
        self.result_label.setPixmap(QPixmap(self.final_print_path).scaled(
            self.s(600), self.s(600),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ))

    def create_printing_page(self):
        page = QWidget(); self.apply_window_style(page, "print")
        layout = QVBoxLayout(page); layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t = QLabel("Print"); t.setStyleSheet(f"font-size: {self.fs(110)}px; font-weight: 600;")
        s = QLabel("잠시만 기다려주세요"); s.setStyleSheet(f"font-size: {self.fs(65)}px; font-weight: 600;")
        self.lbl_print_preview = QLabel(); self.lbl_print_preview.setFixedSize(self.s(500), self.s(750)); self.lbl_print_preview.setStyleSheet("border: 5px solid white; border-radius: 20px; background: #ccc;"); self.lbl_print_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(t, alignment=Qt.AlignmentFlag.AlignCenter); layout.addWidget(s, alignment=Qt.AlignmentFlag.AlignCenter); layout.addSpacing(self.s(50)); layout.addWidget(self.lbl_print_preview, alignment=Qt.AlignmentFlag.AlignCenter)
        return page

    def create_admin_page(self):
        page = QWidget()
        page.setStyleSheet("background: #F0F0F0;")
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        lbl = QLabel("🔧 관리자 설정")
        lbl.setStyleSheet(f"font-size: {self.fs(80)}px; font-weight: 600; color: #333;")
        layout.addWidget(lbl)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedSize(self.s(1600), self.s(800))
        
        panel = QWidget()
        panel.setStyleSheet("background: white; border-radius: 20px;")
        self.admin_layout = QVBoxLayout(panel)
        self.admin_layout.setContentsMargins(40, 40, 40, 40)
        self.admin_layout.setSpacing(15)
        
        # 🔥 add_row 함수 (올바른 위치 - 최상위)
        def add_row(t, k, min_v, max_v, step=1):
            r = QWidget()
            h = QHBoxLayout(r)
            h.setSpacing(self.s(10))
            h.setContentsMargins(0, 0, 0, 0)
            
            l = QLabel(t)
            l.setFixedWidth(self.s(400))
            l.setStyleSheet(f"font-size: {self.fs(32)}px; font-weight: 600; color: black;")
            
            v = QLabel(str(self.admin_settings.get(k)))
            v.setFixedWidth(self.s(100))
            v.setStyleSheet(f"font-size: {self.fs(32)}px; color: blue; background: transparent;")
            v.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            b1 = QPushButton("-")
            b1.setFixedSize(self.s(60), self.s(60))
            b1.setStyleSheet(f"""
                QPushButton {{
                    font-size: {self.fs(36)}px;
                    font-weight: bold;
                    background-color: #E0E0E0;
                    border: 2px solid #999;
                    border-radius: {self.s(10)}px;
                    color: black;
                }}
                QPushButton:hover {{
                    background-color: #D0D0D0;
                }}
                QPushButton:pressed {{
                    background-color: #C0C0C0;
                }}
            """)
            
            b2 = QPushButton("+")
            b2.setFixedSize(self.s(60), self.s(60))
            b2.setStyleSheet(f"""
                QPushButton {{
                    font-size: {self.fs(36)}px;
                    font-weight: bold;
                    background-color: #E0E0E0;
                    border: 2px solid #999;
                    border-radius: {self.s(10)}px;
                    color: black;
                }}
                QPushButton:hover {{
                    background-color: #D0D0D0;
                }}
                QPushButton:pressed {{
                    background-color: #C0C0C0;
                }}
            """)
            
            def upd(d):
                current_val = int(v.text())
                new_val = current_val + (d * step)
                if min_v <= new_val <= max_v:
                    v.setText(str(new_val))
                    self.admin_settings[k] = new_val
                    print(f"[DEBUG] {k} 변경: {new_val}")
            
            b1.clicked.connect(lambda: upd(-1))
            b2.clicked.connect(lambda: upd(1))
            
            h.addWidget(l)
            h.addWidget(b1)
            h.addWidget(v)
            h.addWidget(b2)
            h.addStretch()
            
            self.admin_layout.addWidget(r)
        
        def add_tog(t, k):
            r = QWidget()
            h = QHBoxLayout(r)
            l = QLabel(t)
            l.setFixedWidth(self.s(400))
            l.setStyleSheet(f"font-size: {self.fs(32)}px; font-weight: 600; color: black;")
            s = self.admin_settings.get(k)
            b = QPushButton("ON" if s else "OFF")
            b.setFixedSize(self.s(150), self.s(60))
            b.setStyleSheet(f"font-size: {self.fs(30)}px; color: white; background-color: {'#4CAF50' if s else '#F44336'}; border-radius: 10px;")
            
            def tog():
                n = 0 if b.text() == "ON" else 1
                self.admin_settings[k] = n
                b.setText("ON" if n else "OFF")
                b.setStyleSheet(f"font-size: {self.fs(30)}px; color: white; background-color: {'#4CAF50' if n else '#F44336'}; border-radius: 10px;")
            
            b.clicked.connect(tog)
            h.addWidget(l)
            h.addWidget(b)
            self.admin_layout.addWidget(r)

        def add_cmb(t, k, opts):
            r = QWidget()
            h = QHBoxLayout(r)
            l = QLabel(t)
            l.setFixedWidth(self.s(400))
            l.setStyleSheet(f"font-size: {self.fs(32)}px; font-weight: 600; color: black;")
            c = QComboBox()
            c.setFixedHeight(self.s(60))
            c.setStyleSheet(f"""
                QComboBox {{
                    font-size: {self.fs(30)}px;
                    color: black;
                    background-color: #f0f0f0;
                    border: 2px solid #ccc;
                    border-radius: 10px;
                    padding: 5px;
                }}
                QComboBox::drop-down {{
                    subcontrol-origin: padding;
                    subcontrol-position: top right;
                    width: 40px;
                    border-left-width: 1px;
                    border-left-color: darkgray;
                    border-left-style: solid;
                }}
            """)
            
            for kv, vv in opts.items():
                c.addItem(vv, kv)
            idx = c.findData(self.admin_settings.get(k))
            if idx >= 0:
                c.setCurrentIndex(idx)
            c.currentIndexChanged.connect(lambda i: self.admin_settings.update({k: c.itemData(i)}))
            h.addWidget(l)
            h.addWidget(c)
            self.admin_layout.addWidget(r)

        # 🔥 기본 설정
        l1 = QLabel("기본 설정")
        l1.setStyleSheet(f"font-size: {self.fs(40)}px; font-weight: 600; margin-top: 20px; color: black;")
        self.admin_layout.addWidget(l1)
        add_cmb("결제 방식", "payment_mode", {1: "유상결제 (카드/현금/쿠폰)", 0: "무상결제 (이벤트)", 2: "코인결제 (코인기)"})
        add_row("코인 단가", "coin_price_per_sheet", 1, 10)
        
        # 🔥 가격 설정
        l2 = QLabel("가격 설정")
        l2.setStyleSheet(f"font-size: {self.fs(40)}px; font-weight: 600; margin-top: 20px; color: black;")
        self.admin_layout.addWidget(l2)
        add_row("Full Price", "price_full", 0, 20000, 500)
        add_row("Half Price", "price_half", 0, 20000, 500)
        add_tog("카드 결제", "use_card")
        add_tog("현금 결제", "use_cash")
        add_tog("쿠폰 결제", "use_coupon")
        add_tog("다크 모드", "use_dark_mode")
        
        # 🔥 출력 수량 설정
        l3 = QLabel("출력 수량 설정 (2의 배수)")
        l3.setStyleSheet(f"font-size: {self.fs(40)}px; font-weight: 600; margin-top: 20px; color: black;")
        self.admin_layout.addWidget(l3)
        add_row("최소 수량 (Min)", "print_count_min", 2, 12, step=2)
        add_row("최대 수량 (Max)", "print_count_max", 2, 12, step=2)
        
        # 🔥 촬영 설정
        l4 = QLabel("촬영 설정")
        l4.setStyleSheet(f"font-size: {self.fs(40)}px; font-weight: 600; margin-top: 20px; color: black;")
        self.admin_layout.addWidget(l4)
        add_row("총 촬영 컷수", "total_shoot_count", 1, 12, step=1)
        add_row("촬영 타이머 (초)", "shot_countdown", 1, 10, step=1)

        # 카메라 설정 섹션
        l5 = QLabel("카메라 설정")
        l5.setStyleSheet(f"font-size: {self.fs(40)}px; font-weight: 600; margin-top: 20px; color: black;")
        self.admin_layout.addWidget(l5)
        
        # 카메라 인덱스 설정
        add_row("카메라 인덱스", "camera_index", 0, 5, step=1)
        
        # 카메라 테스트 버튼
        test_camera_row = QWidget()
        test_camera_layout = QHBoxLayout(test_camera_row)
        test_camera_layout.setContentsMargins(0, 0, 0, 0)
        
        test_lbl = QLabel("카메라 연결 테스트")
        test_lbl.setFixedWidth(self.s(400))
        test_lbl.setStyleSheet(f"font-size: {self.fs(32)}px; font-weight: 600; color: black;")
        
        btn_test = QPushButton("테스트 실행")
        btn_test.setFixedSize(self.s(200), self.s(60))
        btn_test.setStyleSheet(f"""
            QPushButton {{
                font-size: {self.fs(28)}px;
                background-color: #2196F3;
                color: white;
                border-radius: 10px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #1976D2;
            }}
            QPushButton:pressed {{
                background-color: #0D47A1;
            }}
        """)
        btn_test.clicked.connect(self.test_camera_connection)
        
        test_camera_layout.addWidget(test_lbl)
        test_camera_layout.addWidget(btn_test)
        test_camera_layout.addStretch()
        
        self.admin_layout.addWidget(test_camera_row)
        
        scroll.setWidget(panel)
        layout.addWidget(scroll)
        
        ex = QPushButton("나가기 (저장)")
        ex.setFixedSize(self.s(500), self.s(100))
        ex.setStyleSheet(f"font-size: {self.fs(45)}px; background: #ff007f; color: white; border-radius: 20px;")
        ex.clicked.connect(lambda: self.show_page(0))
        layout.addWidget(ex)
        
        return page

    def process_timer_tick(self):
        self.remaining_time -= 1
        idx = self.stack.currentIndex()
        target_lbl = None
        if idx == 1: target_lbl = getattr(self, 'lbl_timer_frame', None)
        elif idx == 2: target_lbl = getattr(self, 'lbl_timer_payment', None)
        elif idx == 4: target_lbl = getattr(self, 'lbl_timer_select', None)
        elif idx == 5: target_lbl = getattr(self, 'lbl_timer_filter', None)  # 🔥 추가
        if target_lbl: target_lbl.setText(str(self.remaining_time))
        if self.remaining_time <= 0: self.on_timeout()

    def on_timeout(self):
        """타이머 만료 처리"""
        idx = self.stack.currentIndex()
        self.timer.stop()
        
        if idx == 4:  # 🔥 사진 선택 화면
            # 미선택된 슬롯이 있으면 랜덤으로 채우기
            if None in self.selected_indices:
                print("[DEBUG] 타이머 만료 - 랜덤 선택 시작")
                empty_slots = [i for i, x in enumerate(self.selected_indices) if x is None]
                
                if self.captured_files:
                    for slot_idx in empty_slots:
                        # 촬영된 사진 중 랜덤 선택
                        random_photo = random.choice(range(len(self.captured_files)))
                        self.selected_indices[slot_idx] = random_photo
                    
                    print(f"[DEBUG] 랜덤 선택 결과: {self.selected_indices}")
            
            # 선택 완료 처리
            self.confirm_selection()
        
        elif idx == 5:  # 필터 화면
            self.start_printing()
        
        else:  # 기타 화면
            self.show_page(0)

    def cleanup_files(self):
        if not self.admin_settings.get('save_raw_files'):
            for f in glob.glob("data/original/*.jpg"): 
                try: os.remove(f)
                except: pass

    def auto_select_and_proceed(self):
        """타이머 만료 시 자동 선택 (on_timeout에서 처리)"""
        pass

    def confirm_selection(self):
        """사진 선택 완료 처리"""
        sp = [self.captured_files[i] for i in self.selected_indices if i is not None]
        fp = self.session_data.get('frame_path')
        l_key = self.session_data.get('layout_key')
        fk = f"{self.session_data['paper_type']}_{l_key}"
        
        # 최종 이미지 생성
        self.final_image_path = merge_4cut_vertical(sp, fp, fk)
        
        # 🔥 필터 페이지로 이동 (조건 없이 무조건)
        self.show_page(5)

    def start_printing(self):
        if not hasattr(self, 'final_print_path'): self.final_print_path = self.final_image_path
        if self.session_data.get('use_qr', True): add_qr_to_image(self.final_print_path)
        self.last_printed_file = self.final_print_path
        qty = self.session_data.get('print_qty', 1); current_os = sys.platform
        try: 
            for _ in range(qty): 
                if current_os == 'darwin': subprocess.run(['lpr', '-P', self.admin_settings.get('printer_name', 'Canon_E560_series'), '-o', 'fit-to-page', self.final_print_path])
                elif current_os == 'win32': os.startfile(self.final_print_path, "print")
        except: pass
        self.show_page(6)

    def load_payment_page_logic(self):
        min_q = max(2, self.admin_settings.get('print_count_min', 2))
        self.session_data['print_qty'] = min_q
        self.update_total_price()
        self.update_button_ui()

        # 🔥 실시간 여백 업데이트 로직 추가
        mode = self.admin_settings.get("payment_mode", 1)
        # 여기서 수치를 조정해 보세요 (예: 160 -> 250)
        top_margin = 150 if mode == 0 else 60 
    
        if hasattr(self, 'content_v_layout'):
            self.content_v_layout.setContentsMargins(0, self.s(top_margin), 0, 0)
            print(f"[DEBUG] 결제 페이지 마진 업데이트: {top_margin}px (Mode: {mode})")

        while self.payment_btn_layout.count():
            item = self.payment_btn_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        m = self.admin_settings.get("payment_mode", 1)
        if m == 0: 
            self.c_prc.hide()
            b = GradientButton("촬영 시작", "Start", self, self.s)
            b.clicked.connect(lambda: self.payment_success('free'))
            self.payment_btn_layout.addWidget(b)
        else: 
            self.c_prc.show()
            if m == 1:
                if self.admin_settings.get("use_card"):
                    b = GradientButton("카드 결제", "Card", self, self.s); b.clicked.connect(lambda: self.show_payment_popup("card")); self.payment_btn_layout.addWidget(b)
                if self.admin_settings.get("use_cash"):
                    b = GradientButton("현금 결제", "Cash", self, self.s); b.clicked.connect(lambda: self.show_payment_popup("cash")); self.payment_btn_layout.addWidget(b)
                if self.admin_settings.get("use_coupon"):
                    b = GradientButton("쿠폰 적용", "Coupon", self, self.s); b.clicked.connect(self.show_coupon_input); self.payment_btn_layout.addWidget(b)
            elif m == 2:
                b = GradientButton("코인 결제", "Coin", self, self.s); b.clicked.connect(lambda: self.show_payment_popup("coin")); self.payment_btn_layout.addWidget(b)

    def show_payment_popup(self, m):
        self.payment_popup_dialog = PaymentPopup(self, self.admin_settings.get("use_dark_mode"), self.s, m)
        self.payment_popup_dialog.show()

        # 팝업 닫으면 (X 누르거나 취소) -> 늦게 오는 승인 결과 무시
        self._payment_cancelled = False
        self.payment_popup_dialog.rejected.connect(lambda: setattr(self, "_payment_cancelled", True))

        # 카드 결제만 실승인으로 처리 (나머지는 기존처럼 바로 성공 처리해도 됨)
        if m != "card":
            self.payment_success(m)
            return

        # 결제 금액 가져오기
        amount = int(self.session_data.get("total_price", 0))
        if amount <= 0:
            QMessageBox.warning(self, "결제 오류", "결제 금액이 0원입니다. 가격 설정/선택을 확인하세요.")
            self.payment_popup_dialog.reject()
            return

        # 중복 결제 방지 (버튼 연타 방지)
        if getattr(self, "_payment_in_progress", False):
            return
        self._payment_in_progress = True

        # KSCAT 승인 요청: UI 멈추지 않게 스레드에서 실행
        self.payment_thread = PaymentApproveThread(amount=amount, parent=self)
        self.payment_thread.finished.connect(self.on_card_payment_result)
        self.payment_thread.start()

    def on_card_payment_result(self, result: dict):
        self._payment_in_progress = False

        # 사용자가 팝업을 닫았으면 결과 무시
        if getattr(self, "_payment_cancelled", False):
            return

        if result.get("success"):
            # 성공: 팝업 닫고 촬영 페이지로 이동
            if getattr(self, "payment_popup_dialog", None):
                self.payment_popup_dialog.accept()
                self.payment_popup_dialog = None

            # 로그/기록용 (원하면 제거 가능)
            self.session_data["payment_raw"] = result.get("raw", "")
            self.payment_success("card")  # 여기서 show_page(3)으로 넘어감
        else:
            # 실패: 팝업은 열린 상태로 두고 경고만
            msg = result.get("message", "결제 실패")
            QMessageBox.warning(self, "결제 실패", msg)



    def on_payment_approved(self, m):
        if hasattr(self, 'payment_popup_dialog') and self.payment_popup_dialog: self.payment_popup_dialog.accept(); self.payment_popup_dialog = None
        self.payment_success(m)
    
    def show_coupon_input(self): self.coupon_widget.show()
    def payment_success(self, m): self.session_data.update({'payment_method': m, 'use_qr': self.chk_qr.isChecked()}); self.show_page(3)

    def select_frame_and_go(self, item):
        self.session_data.update({"paper_type": item['paper'], "layout_key": item['layout'], "frame_path": item['path']})
        # 레이아웃 이름에서 숫자 추출 (예: v4a -> 4)
        import re; nums = re.findall(r'\d+', item['layout'])
        self.session_data['target_count'] = int(nums[0]) if nums else 4
        self.show_page(2)
    
    def load_frame_options(self):
        for i in reversed(range(self.frame_grid.count())): 
            if self.frame_grid.itemAt(i).widget(): 
                self.frame_grid.itemAt(i).widget().setParent(None)
        
        papers = self.event_config.get("papers", {})
        all_frames = []
        for p_type, layouts in papers.items():
            for l_key, files in layouts.items():
                d = os.path.join(self.asset_root, p_type, l_key)
                if not os.path.exists(d): continue
                if "*" in files:
                    fs = sorted(glob.glob(os.path.join(d, "*.png")))
                else:
                    fs = [os.path.join(d, f) for f in files if os.path.exists(os.path.join(d, f))]
                for fp in fs:
                    if os.path.basename(fp).endswith("_btn.png"): continue
                    bn = os.path.splitext(os.path.basename(fp))[0]
                    btn_p = os.path.join(d, f"{bn}_btn.png")
                    all_frames.append({ "path": fp, "btn_path": btn_p if os.path.exists(btn_p) else fp, "paper": p_type, "layout": l_key, "name": bn })
        
        # 🔥 프레임 개수에 따라 스크롤/일반 위젯 전환
        frame_count = len(all_frames)
        
        # 🔥 기존 위젯 제거
        if self.scroll_area.parent():
            self.frame_container_layout.removeWidget(self.scroll_area)
            self.scroll_area.setParent(None)
        if self.no_scroll_area.parent():
            self.frame_container_layout.removeWidget(self.no_scroll_area)
            self.no_scroll_area.setParent(None)
        
        if frame_count <= 4:
            # 🔥 4개 이하: 일반 위젯 + 상하 중앙 정렬
            # no_scroll_area에 frame_grid_widget 재부착
            if self.frame_grid_widget.parent() == self.scroll_area:
                self.scroll_area.takeWidget()
            no_scroll_layout = self.no_scroll_area.layout()
            if not no_scroll_layout:
                no_scroll_layout = QVBoxLayout(self.no_scroll_area)
                no_scroll_layout.setContentsMargins(0, 0, 0, 0)
            else:
                # 기존 위젯 제거
                while no_scroll_layout.count():
                    item = no_scroll_layout.takeAt(0)
                    if item.widget():
                        item.widget().setParent(None)
            no_scroll_layout.addWidget(self.frame_grid_widget)
            
            self.frame_container_layout.addWidget(self.no_scroll_area)
            self.grid_vertical_layout.setStretch(0, 1)  # 상단
            self.grid_vertical_layout.setStretch(2, 1)  # 하단
            
        elif frame_count <= 8:
            # 🔥 5~8개: 일반 위젯 + 상단 정렬 (스크롤 없음)
            # no_scroll_area에 frame_grid_widget 재부착
            if self.frame_grid_widget.parent() == self.scroll_area:
                self.scroll_area.takeWidget()
            no_scroll_layout = self.no_scroll_area.layout()
            if not no_scroll_layout:
                no_scroll_layout = QVBoxLayout(self.no_scroll_area)
                no_scroll_layout.setContentsMargins(0, 0, 0, 0)
            else:
                # 기존 위젯 제거
                while no_scroll_layout.count():
                    item = no_scroll_layout.takeAt(0)
                    if item.widget():
                        item.widget().setParent(None)
            no_scroll_layout.addWidget(self.frame_grid_widget)
            
            self.frame_container_layout.addWidget(self.no_scroll_area)
            self.grid_vertical_layout.setStretch(0, 0)  # 상단
            self.grid_vertical_layout.setStretch(2, 1)  # 하단
            
        else:
            # 🔥 9개 이상: 스크롤 영역 사용
            # scroll_area에 frame_grid_widget 재부착
            if self.frame_grid_widget.parent() == self.no_scroll_area:
                no_scroll_layout = self.no_scroll_area.layout()
                if no_scroll_layout:
                    no_scroll_layout.removeWidget(self.frame_grid_widget)
                    self.frame_grid_widget.setParent(None)
            
            self.scroll_area.setWidget(self.frame_grid_widget)
            self.frame_container_layout.addWidget(self.scroll_area)
            self.grid_vertical_layout.setStretch(0, 0)  # 상단
            self.grid_vertical_layout.setStretch(2, 0)  # 하단
        
        bs, fs = self.s(300), self.s(20)
        for i, item in enumerate(all_frames):
            c = QWidget()
            v = QVBoxLayout(c)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(self.s(10))
            v.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            b = QPushButton()
            b.setFixedSize(bs, bs)
            b.setStyleSheet(f"QPushButton {{ border-image: url('{item['btn_path'].replace(os.sep, '/')}'); border-radius: {self.s(50)}px; border: none; background-color: transparent; }}")
            b.clicked.connect(lambda _, it=item: self.select_frame_and_go(it))
            
            l = QLabel(item["name"])
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.setStyleSheet(f"font-family: 'Pretendard SemiBold'; font-size: {fs}px; color: black; background: transparent;")
            
            v.addWidget(b)
            v.addWidget(l)
            
            self.frame_grid.addWidget(c, i//4, i%4)

    def update_print_qty(self, delta):
        current = self.session_data.get('print_qty', 2)
        min_q = self.admin_settings.get('print_count_min', 2)
        max_q = self.admin_settings.get('print_count_max', 12)
        
        new_qty = current + (delta * 2)
        if min_q <= new_qty <= max_q:
            self.session_data['print_qty'] = new_qty
            # 1. '장' 단위 표시
            self.lbl_qty.setText(f"{new_qty}장")
            self.update_total_price()
            self.update_button_ui()

    def update_total_price(self):
        qty = self.session_data.get('print_qty', 2)
        paper_type = self.session_data.get('paper_type', 'full')
        price_per_sheet = self.admin_settings.get(f'price_{paper_type}', 4000)
        total = price_per_sheet * (qty // 2)

        self.lbl_price.setText(f"{total:,}원")

        # ✅ 결제 요청에 쓸 금액 저장 (필수)
        self.session_data["total_price"] = total


    def update_button_ui(self):
        """버튼 활성화/비활성화 업데이트"""
        current = self.session_data.get('print_qty', 2)
        min_q = self.admin_settings.get('print_count_min', 2)
        max_q = self.admin_settings.get('print_count_max', 12)
        
        # 🔥 1. 최소 = 최대인 경우 버튼 완전 투명 (정렬 유지)
        if min_q == max_q:
            self.btn_minus.setEnabled(False)
            self.btn_minus.setGraphicsEffect(self._create_opacity_effect(0.0))
            self.btn_plus.setEnabled(False)
            self.btn_plus.setGraphicsEffect(self._create_opacity_effect(0.0))
            return
        
        # 🔥 2. 마이너스 버튼: 최소일 때 30% 투명도
        if current <= min_q:
            self.btn_minus.setEnabled(False)
            self.btn_minus.setGraphicsEffect(self._create_opacity_effect(0.3))
        else:
            self.btn_minus.setEnabled(True)
            self.btn_minus.setGraphicsEffect(self._create_opacity_effect(1.0))
        
        # 🔥 3. 플러스 버튼: 최대일 때 30% 투명도
        if current >= max_q:
            self.btn_plus.setEnabled(False)
            self.btn_plus.setGraphicsEffect(self._create_opacity_effect(0.3))
        else:
            self.btn_plus.setEnabled(True)
            self.btn_plus.setGraphicsEffect(self._create_opacity_effect(1.0))

    def _create_opacity_effect(self, opacity):
        """투명도 효과 생성 (배경+테두리+아이콘 모두 적용)"""
        effect = QGraphicsOpacityEffect()
        effect.setOpacity(opacity)
        return effect

    def load_payment_page(self):
        """결제 페이지 로드 시 호출"""
        self.load_payment_page_logic()

    def update_image(self, qt_img):
        """카메라 영상 처리 및 화면 표시 (카운트다운 오버레이 추가됨)"""
        # 1. 거울 모드 적용
        if self.admin_settings.get('mirror_mode'): 
            qt_img = qt_img.mirrored(True, False)
        
        self.current_frame_data = qt_img.copy()
        
        # 2. 화면 표시를 위한 타겟 크기
        target_w = self.video_label.width()
        target_h = self.video_label.height()
        if target_w <= 0 or target_h <= 0: return
        
        # 3. 프레임 레이아웃 정보 가져오기
        paper = self.session_data.get('paper_type', 'full')
        layout = self.session_data.get('layout_key', 'v2')
        key = f"{paper}_{layout}"
        layout_list = FRAME_LAYOUTS.get(key, [])
        
        slot_info = None
        if layout_list:
            idx = (self.current_shot_idx - 1) % len(layout_list) if hasattr(self, 'current_shot_idx') else 0
            slot_info = layout_list[idx]
        
        # 🔥 4. 현재 컷의 프레임 비율 계산
        if slot_info:
            slot_ratio = slot_info['w'] / slot_info['h']  # 예: 1100/1600 = 0.6875
        else:
            slot_ratio = 3 / 4  # 기본 비율
        
        # 🔥 5. 화면을 프레임 비율에 맞게 영역 계산
        screen_ratio = target_w / target_h
        
        if screen_ratio > slot_ratio:
            # 화면이 더 넓음 -> 좌우 여백
            display_h = target_h
            display_w = int(display_h * slot_ratio)
            display_x = (target_w - display_w) // 2
            display_y = 0
        else:
            # 화면이 더 좁음 -> 위아래 여백
            display_w = target_w
            display_h = int(display_w / slot_ratio)
            display_x = 0
            display_y = (target_h - display_h) // 2
        
        # 🔥 6. 캔버스 생성 및 카메라 영상 배치
        final_pixmap = QPixmap(target_w, target_h)
        final_pixmap.fill(Qt.GlobalColor.black)
        
        painter = QPainter(final_pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 카메라 영상을 계산된 영역에 꽉 채우기
        cam_pixmap = QPixmap.fromImage(qt_img)
        scaled_cam = cam_pixmap.scaled(
            display_w, display_h,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation
        )
        
        # 중앙 크롭
        crop_x = (scaled_cam.width() - display_w) // 2
        crop_y = (scaled_cam.height() - display_h) // 2
        painter.drawPixmap(display_x, display_y, scaled_cam, crop_x, crop_y, display_w, display_h)
        
        # 🔥 7. 프레임 오버레이 (현재 컷 영역만)
        frame_path = self.session_data.get('frame_path')
        if frame_path and os.path.exists(frame_path) and slot_info:
            try:
                # 프레임 원본 이미지 로드 (2400x3600)
                frame_full = QPixmap(frame_path)
                
                # 현재 컷 영역만 크롭
                frame_cropped = frame_full.copy(
                    slot_info['x'], 
                    slot_info['y'], 
                    slot_info['w'], 
                    slot_info['h']
                )
                
                # 계산된 영역에 맞게 스케일
                frame_scaled = frame_cropped.scaled(
                    display_w, display_h,
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                
                # 🔥 완전 불투명 (1.0)
                painter.setOpacity(1.0)
                painter.drawPixmap(display_x, display_y, frame_scaled)
                
            except Exception as e:
                print(f"프레임 오버레이 오류: {e}")
            
        painter.end()
        self.video_label.setPixmap(final_pixmap)

    def show_page(self, idx):
         # 🔥 페이지 전환 시 크기 강제 설정
        if hasattr(self, 'stack') and hasattr(self, 'new_w'):
            target_w = int(self.new_w)
            target_h = int(self.new_h)
            
            print(f"\n[DEBUG] === 페이지 {idx} 전환 ===")
            print(f"[DEBUG] 목표 크기: {target_w} x {target_h}")
            
            # 스택 크기 재설정
            self.stack.setGeometry(0, 0, target_w, target_h)
            
            # 모든 페이지 위젯 강제 리사이징
            for i in range(self.stack.count()):
                widget = self.stack.widget(i)
                if widget:
                    widget.setGeometry(0, 0, target_w, target_h)
                    widget.resize(target_w, target_h)
                    widget.updateGeometry()
            
            print(f"[DEBUG] 모든 페이지 리사이징 완료")
        
        if idx == 99: 
            self.stack.setCurrentWidget(self.page_admin)
            self.timer.stop()
            return
        if idx==0: self.cleanup_files(); self.selected_indices=[]
        self.stack.setCurrentIndex(idx)
        if idx==1: self.load_frame_options() 
        elif idx==2: self.load_payment_page()
        elif idx==3:
            # 🔥 기존 테더링 방식 (주석 처리)
            # camera_index = self.admin_settings.get('camera_index', 0)
            # self.cam_thread = VideoThread(camera_index=camera_index)
            # self.cam_thread.change_pixmap_signal.connect(self.update_image)
            # self.cam_thread.start()
            # 
            # shoot_n = self.get_admin_shoot_count()
            # timeout = 20 + shoot_n * 5
            # 
            # self.tether_thread = TetherCaptureManyThread(
            #     expected_count=shoot_n, 
            #     timeout_sec=timeout, 
            #     parent=self
            # )
            # self.tether_thread.success.connect(self.on_tether_success_many)
            # self.tether_thread.failed.connect(self.on_tether_failed)
            # self.tether_thread.start()
            
            # 🔥 새로운 방식: camera_manager 독립 실행
            self.run_external_camera_manager()

        elif idx==4:
            print("[DEBUG] 사진 선택 페이지 진입")
            print(f"[DEBUG] session_data: {self.session_data}")
            
            # 카메라 스레드 확인 및 종료
            if self.cam_thread:
                print("[DEBUG] 잔여 카메라 스레드 발견 - 종료")
                try:
                    self.cam_thread.change_pixmap_signal.disconnect()
                except:
                    pass
                self.cam_thread.stop()
                self.cam_thread.wait(1000)
                self.cam_thread = None
            
            # 🔥 페이지를 매번 재생성 (session_data 반영)
            old_widget = self.stack.widget(4)
            if old_widget:
                self.stack.removeWidget(old_widget)
                old_widget.deleteLater()
            
            self.page_select = self.create_select_page()
            self.stack.insertWidget(4, self.page_select)
            self.stack.setCurrentIndex(4)
            
            # 선택 인덱스 초기화
            target_count = self.session_data.get('target_count', 4)
            self.selected_indices = [None] * target_count
            
            # 페이지 로드
            self.load_select_page()
            print("[DEBUG] 사진 선택 페이지 로드 완료")
        elif idx==5: 
            # 🔥 좌우반전 상태 초기화 (ON으로 시작)
            self.is_mirrored = True
            
            # 원본 프레임 합성
            sp = [self.captured_files[i] for i in self.selected_indices if i is not None]
            fp = self.session_data.get('frame_path')
            l_key = self.session_data.get('layout_key')
            fk = f"{self.session_data['paper_type']}_{l_key}"
            
            # 🔥 초기에 좌우반전 적용된 상태로 합성
            mirrored_photos = []
            for photo_path in sp:
                img = QPixmap(photo_path)
                img = img.toImage().mirrored(True, False)
                img = QPixmap.fromImage(img)
                temp_path = photo_path.replace('.jpg', '_temp_mirror.jpg')
                img.save(temp_path)
                mirrored_photos.append(temp_path)
            
            self.final_image_path = merge_4cut_vertical(mirrored_photos, fp, fk)
            self.final_print_path = self.final_image_path
            self.current_filter_mode = "original"
            
            self.result_label.setPixmap(QPixmap(self.final_image_path).scaled(
                self.s(600), self.s(600), 
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))
        elif idx==6:
            if hasattr(self, 'final_print_path') and os.path.exists(self.final_print_path):
                pix = QPixmap(self.final_print_path); self.lbl_print_preview.setPixmap(pix.scaled(self.lbl_print_preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.timer.stop()
        t = 0
        if idx==1: t = self.admin_settings.get('timeout_frame', 60)
        elif idx==2: t = self.admin_settings.get('timeout_payment', 60)
        elif idx==4: t = 40
        elif idx==5: t = self.admin_settings.get('timeout_filter', 60)
        elif idx==6: t = self.admin_settings.get('timeout_print', 30)
        
        if t > 0:
            self.remaining_time = t
            if idx == 1 and hasattr(self, 'lbl_timer_frame'):
                self.lbl_timer_frame.setText(str(t))
            elif idx == 2 and hasattr(self, 'lbl_timer_payment'):
                self.lbl_timer_payment.setText(str(t))
            elif idx == 4 and hasattr(self, 'lbl_timer_select'):
                self.lbl_timer_select.setText(str(t))
            elif idx == 5 and hasattr(self, 'lbl_timer_filter'):  # 🔥 추가
                self.lbl_timer_filter.setText(str(t))
            self.timer.start(1000)


    def on_tether_success(self, photo_path: str):
        print("[tether] captured:", photo_path)

        # 예약된 촬영 시작 타이머 취소
        if hasattr(self, "shoot_timer") and self.shoot_timer:
            self.shoot_timer.stop()
            self.shoot_timer = None

        # 카메라 스레드도 종료(프리뷰만 쓰는 구조로 갈 때)
        if hasattr(self, "cam_thread") and self.cam_thread:
            self.cam_thread.stop()
            self.cam_thread = None

        self.saved_photos = [photo_path]
        self.show_page(4)

    def on_tether_failed(self, msg: str):
        print("[tether] failed:", msg)

        # 테더 실패했을 때만 웹캠 촬영 시작 (fallback)
        self.shoot_timer = QTimer(self)
        self.shoot_timer.setSingleShot(True)
        self.shoot_timer.timeout.connect(self.start_shooting)
        self.shoot_timer.start(1000)

    def on_tether_success_many(self, photo_paths):
        print("[tether] captured many:", len(photo_paths))

        # 프리뷰/촬영 예약 취소류
        if hasattr(self, "shoot_timer") and self.shoot_timer:
            self.shoot_timer.stop()
            self.shoot_timer = None

        if hasattr(self, "cam_thread") and self.cam_thread:
            self.cam_thread.stop()
            self.cam_thread = None

        # ✅ 핵심: 선택 페이지가 쓰는 리스트를 테더 결과로 갱신
        self.captured_files = list(photo_paths)
        self.saved_photos = list(photo_paths)  # (원하면 유지)

        self.show_page(4)

    # 🔥 여기에 추가!
    def run_external_camera_manager(self):
        """외부 camera_manager.py 실행 및 결과 대기"""
        import subprocess
        import json
        
        # 1. 결과 파일 삭제 (이전 세션)
        result_path = 'camera_result.json'
        if os.path.exists(result_path):
            os.remove(result_path)
        
        # 2. camera_manager.py 실행
        python_exe = sys.executable
        script_path = os.path.join(self.base_path, 'camera_manager.py')
        
        print(f"[외부 촬영] {script_path} 실행 중...")
        
        try:
            process = subprocess.Popen(
                [python_exe, script_path, '--standalone'],
                cwd=self.base_path
            )
            
            self.hide()
            self.wait_for_camera_result(process, result_path)
            
        except Exception as e:
            print(f"[외부 촬영] 오류: {e}")
            QMessageBox.critical(self, "촬영 오류", f"촬영 프로그램 실행 실패:\n{e}")
            self.show()
            self.show_page(0)


    def wait_for_camera_result(self, process, result_path):
        """camera_manager 종료 및 결과 파일 대기"""
        import json
        
        check_timer = QTimer(self)
        check_count = 0
        max_checks = 300
        
        def check_result():
            nonlocal check_count
            check_count += 1
            
            if process.poll() is not None:
                check_timer.stop()
                
                if os.path.exists(result_path):
                    try:
                        with open(result_path, 'r', encoding='utf-8') as f:
                            result = json.load(f)
                        
                        if result.get('success'):
                            self.captured_files = result['files']
                            print(f"[외부 촬영] 성공: {len(self.captured_files)}개")
                            self.show()
                            self.show_page(4)
                        else:
                            self.show()
                            QMessageBox.warning(self, "촬영 실패", "촬영이 완료되지 않았습니다.")
                            self.show_page(0)
                    
                    except Exception as e:
                        print(f"[외부 촬영] 결과 로드 오류: {e}")
                        self.show()
                        self.show_page(0)
                else:
                    print("[외부 촬영] 결과 파일 없음")
                    self.show()
                    self.show_page(0)
            
            elif check_count >= max_checks:
                check_timer.stop()
                process.terminate()
                self.show()
                QMessageBox.warning(self, "촬영 시간 초과", "촬영 시간이 초과되었습니다.")
                self.show_page(0)
        
        check_timer.timeout.connect(check_result)
        check_timer.start(1000)


    
    # -----------------------------------------------------------
    # [Shooting Logic] - 구현 완료된 촬영 로직
    # -----------------------------------------------------------
    def start_shooting(self):
        """촬영 시퀀스 시작"""
        print("[DEBUG] 촬영 시작")
        
        # 변수 초기화
        self.current_shot_idx = 1
        self.captured_files = []
        self.total_shots = self.admin_settings.get('total_shoot_count', 8)
        self.current_countdown_display = 0
        
        # 미리보기창 동적 생성
        # 기존 위젯 제거
        for lbl in self.left_previews + self.right_previews:
            lbl.deleteLater()
        self.left_previews.clear()
        self.right_previews.clear()
        
        # 🔥 프레임 구멍 비율 계산
        paper = self.session_data.get('paper_type', 'full')
        layout = self.session_data.get('layout_key', 'v2')
        key = f"{paper}_{layout}"
        layout_list = FRAME_LAYOUTS.get(key, [])
        
        if layout_list:
            first_slot = layout_list[0]
            hole_ratio = first_slot['w'] / first_slot['h']
            print(f"[DEBUG] 프레임 구멍 비율: {hole_ratio:.3f} ({first_slot['w']}x{first_slot['h']})")
        else:
            hole_ratio = 3 / 4  # 기본 비율
            print(f"[DEBUG] 기본 비율 사용: {hole_ratio:.3f}")
        
        # 좌우 균등 배분
        left_count = (self.total_shots + 1) // 2
        right_count = self.total_shots // 2
        
        print(f"[DEBUG] 미리보기 배치: 좌측 {left_count}개, 우측 {right_count}개 (총 {self.total_shots}개)")
        
        # 공통 스타일
        preview_style = f"""
            background-color: #333; 
            border-radius: {self.s(10)}px;
            border: none;
        """
        
        # 🔥 사이드바 사용 가능 영역
        sidebar_content_width = self.s(230 - 60)  # 170px (여백 제외)
        sidebar_content_height = int(self.new_h) - self.s(130 + 60)  # 헤더 + 여백 제외
        
        # 🔥 각 미리보기의 크기 계산 (구멍 비율 유지)
        # 좌측
        left_spacing_total = self.s(15) * (left_count - 1) if left_count > 1 else 0
        available_height_left = (sidebar_content_height - left_spacing_total) // left_count if left_count > 0 else 100
        
        # 너비 기준으로 높이 계산 vs 높이 기준으로 너비 계산 중 작은 것 선택
        height_from_width = int(sidebar_content_width / hole_ratio)
        width_from_height = int(available_height_left * hole_ratio)
        
        if height_from_width <= available_height_left:
            # 너비 꽉 채우기
            preview_width_left = sidebar_content_width
            preview_height_left = height_from_width
        else:
            # 높이 꽉 채우기
            preview_width_left = width_from_height
            preview_height_left = available_height_left
        
        # 우측
        right_spacing_total = self.s(15) * (right_count - 1) if right_count > 1 else 0
        available_height_right = (sidebar_content_height - right_spacing_total) // right_count if right_count > 0 else 100
        
        height_from_width_r = int(sidebar_content_width / hole_ratio)
        width_from_height_r = int(available_height_right * hole_ratio)
        
        if height_from_width_r <= available_height_right:
            preview_width_right = sidebar_content_width
            preview_height_right = height_from_width_r
        else:
            preview_width_right = width_from_height_r
            preview_height_right = available_height_right
        
        print(f"[DEBUG] 미리보기 크기: 좌측 {preview_width_left}x{preview_height_left}, 우측 {preview_width_right}x{preview_height_right}")
        
        # 🔥 좌측 미리보기 생성
        for i in range(left_count):
            lbl = QLabel()
            lbl.setStyleSheet(preview_style)
            lbl.setScaledContents(False)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            # 구멍 비율 유지한 크기 설정
            lbl.setFixedSize(preview_width_left, preview_height_left)
            
            self.left_layout.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignCenter)
            self.left_previews.append(lbl)
        
        # 좌측 여백
        self.left_layout.addStretch(1)
        
        # 🔥 우측 미리보기 생성
        for i in range(right_count):
            lbl = QLabel()
            lbl.setStyleSheet(preview_style)
            lbl.setScaledContents(False)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            # 구멍 비율 유지한 크기 설정
            lbl.setFixedSize(preview_width_right, preview_height_right)
            
            self.right_layout.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignCenter)
            self.right_previews.append(lbl)
        
        # 우측 여백
        self.right_layout.addStretch(1)
        
        # 첫 번째 촬영 준비
        QTimer.singleShot(1000, self.prepare_next_shot)

    def prepare_next_shot(self):
        """다음 촬영 준비 (카운트다운 시작)"""
        # 목표 컷수를 다 채웠으면 선택 페이지로 이동
        if self.current_shot_idx > self.total_shots:
            print("[DEBUG] 촬영 완료 - 정리 시작")
            
            # 🔥 1. 타이머 정리
            if hasattr(self, 'shooting_timer') and self.shooting_timer:
                self.shooting_timer.stop()
                self.shooting_timer.deleteLater()
                self.shooting_timer = None
            
            # 🔥 2. 카메라 스레드 완전 종료
            if self.cam_thread:
                print("[DEBUG] 카메라 스레드 종료 중...")
                self.cam_thread.change_pixmap_signal.disconnect()  # 시그널 연결 해제
                self.cam_thread.stop()
                self.cam_thread.wait(2000)  # 최대 2초 대기
                self.cam_thread.deleteLater()
                self.cam_thread = None
                print("[DEBUG] 카메라 스레드 종료 완료")
            
            # 🔥 3. 비디오 라벨 정리
            if hasattr(self, 'video_label'):
                self.video_label.clear()
                self.video_label.setText("처리 중...")
            
            # 🔥 4. 메모리 정리 후 페이지 전환
            QApplication.processEvents()  # 이벤트 처리
            QTimer.singleShot(800, lambda: self.show_page(4))  # 0.8초 후 전환
            return

        # 카운트다운 값 설정
        self.countdown_val = self.admin_settings.get('shot_countdown', 3)
        self.current_countdown_display = self.countdown_val
        
        # 상단 UI 업데이트
        if hasattr(self, 'lbl_shot_count'):
            self.lbl_shot_count.setText(f"{self.current_shot_idx}/{self.total_shots}")
        
        # 카운트다운 타이머 생성 및 시작
        self.shooting_timer = QTimer(self)
        self.shooting_timer.timeout.connect(self.process_countdown)
        self.shooting_timer.start(1000)
        
        # 즉시 1회 실행
        self.process_countdown()

    def test_camera_connection(self):
        """관리자 페이지에서 카메라 연결 테스트"""
        camera_index = self.admin_settings.get('camera_index', 0)
        
        import cv2
        import platform
        
        # 플랫폼별 백엔드로 카메라 열기
        if platform.system() == 'Darwin':  # macOS
            cap = cv2.VideoCapture(camera_index, cv2.CAP_AVFOUNDATION)
        elif platform.system() == 'Windows':
            cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
        else:
            cap = cv2.VideoCapture(camera_index)
        
        if cap.isOpened():
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            backend = cap.getBackendName()
            
            # 프레임 1장 읽어보기
            ret, frame = cap.read()
            
            msg = f"✅ 카메라 #{camera_index} 연결 성공!\n\n"
            msg += f"해상도: {width} x {height}\n"
            msg += f"FPS: {fps:.1f}\n"
            msg += f"Backend: {backend}\n"
            msg += f"프레임 읽기: {'성공' if ret else '실패'}"
            
            QMessageBox.information(
                self,
                "카메라 테스트",
                msg,
                QMessageBox.StandardButton.Ok
            )
            cap.release()
        else:
            msg = f"❌ 카메라 #{camera_index} 연결 실패!\n\n"
            msg += "해결방법:\n"
            msg += "1. Canon EOS Webcam Utility 설치 확인\n"
            msg += "2. 카메라 USB 연결 확인\n"
            msg += "3. 카메라를 동영상 모드로 설정\n"
            msg += "4. check_camera.py로 올바른 인덱스 확인"
            
            QMessageBox.warning(
                self,
                "카메라 테스트",
                msg,
                QMessageBox.StandardButton.Ok
            )

    def on_camera_error(self, error_message):
        """카메라 오류 발생 시 처리 (선택사항)"""
        print(f"[CAMERA ERROR] {error_message}")
        
        QMessageBox.critical(
            self,
            "카메라 오류",
            error_message,
            QMessageBox.StandardButton.Ok
        )
        
        # 메인 화면으로 복귀
        self.show_page(0)


    def process_countdown(self):
        """1초마다 호출: 숫자 감소 -> 촬영"""
        # 헤더 타이머 표시
        if hasattr(self, 'lbl_timer_header'):
            self.lbl_timer_header.setText(str(self.countdown_val) if self.countdown_val > 0 else "Smile!")
        
        # 화면 중앙 표시용 변수 업데이트
        self.current_countdown_display = self.countdown_val

        if self.countdown_val <= 0:
            self.shooting_timer.stop()
            self.take_photo() # 촬영!
        else:
            self.countdown_val -= 1

    def take_photo(self):
        """현재 프레임 저장"""
        if not hasattr(self, 'current_frame_data') or self.current_frame_data is None:
            print("⚠️ 카메라 데이터가 아직 없습니다. 재시도합니다.")
            QTimer.singleShot(500, self.prepare_next_shot)
            return

        # 1. 저장 경로 설정
        save_dir = os.path.join("data", "original")
        os.makedirs(save_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"shot_{timestamp}_{self.current_shot_idx}.jpg"
        filepath = os.path.join(save_dir, filename)
        
        # 2. 이미지 저장
        self.current_frame_data.save(filepath)
        self.captured_files.append(filepath)
        print(f"[Save] {filepath}")
        
        # 🔥 3. 현재 컷의 프레임 구멍 비율 가져오기
        paper = self.session_data.get('paper_type', 'full')
        layout = self.session_data.get('layout_key', 'v2')
        key = f"{paper}_{layout}"
        layout_list = FRAME_LAYOUTS.get(key, [])
        
        # 현재 촬영 컷의 구멍 정보
        slot_idx = (self.current_shot_idx - 1) % len(layout_list) if layout_list else 0
        slot_info = layout_list[slot_idx] if layout_list else None
        
        # 🔥 4. 사이드바 미리보기 업데이트 (최대 크기로)
        all_previews = self.left_previews + self.right_previews
        preview_idx = self.current_shot_idx - 1
        
        if preview_idx < len(all_previews):
            lbl = all_previews[preview_idx]
            pix = QPixmap(filepath)
            
            if slot_info and not pix.isNull():
                # 🔥 구멍 비율 계산
                hole_ratio = slot_info['w'] / slot_info['h']
                
                # 🔥 이미지를 구멍 비율로 크롭
                img_w = pix.width()
                img_h = pix.height()
                img_ratio = img_w / img_h
                
                if img_ratio > hole_ratio:
                    # 이미지가 더 넓음 -> 좌우 자르기
                    crop_h = img_h
                    crop_w = int(crop_h * hole_ratio)
                    crop_x = (img_w - crop_w) // 2
                    crop_y = 0
                else:
                    # 이미지가 더 좁음 -> 위아래 자르기
                    crop_w = img_w
                    crop_h = int(crop_w / hole_ratio)
                    crop_x = 0
                    crop_y = (img_h - crop_h) // 2
                
                # 크롭
                cropped_pix = pix.copy(crop_x, crop_y, crop_w, crop_h)
                
                # 🔥 라벨 크기를 꽉 채우도록 스케일 (KeepAspectRatioByExpanding)
                lbl.setScaledContents(False)
                scaled = cropped_pix.scaled(
                    lbl.width(), 
                    lbl.height(),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,  # 🔥 영역을 꽉 채움
                    Qt.TransformationMode.SmoothTransformation
                )
                
                # 🔥 넘치는 부분은 중앙 크롭
                if scaled.width() > lbl.width() or scaled.height() > lbl.height():
                    final_x = (scaled.width() - lbl.width()) // 2
                    final_y = (scaled.height() - lbl.height()) // 2
                    final_pix = scaled.copy(final_x, final_y, lbl.width(), lbl.height())
                    lbl.setPixmap(final_pix)
                else:
                    lbl.setPixmap(scaled)
                
                print(f"[DEBUG] 미리보기 {preview_idx}: 라벨크기 {lbl.width()}x{lbl.height()}")
            else:
                # 구멍 정보 없으면 기본 표시 (꽉 채우기)
                lbl.setScaledContents(False)
                scaled = pix.scaled(
                    lbl.width(),
                    lbl.height(),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation
                )
                if scaled.width() > lbl.width() or scaled.height() > lbl.height():
                    final_x = (scaled.width() - lbl.width()) // 2
                    final_y = (scaled.height() - lbl.height()) // 2
                    final_pix = scaled.copy(final_x, final_y, lbl.width(), lbl.height())
                    lbl.setPixmap(final_pix)
                else:
                    lbl.setPixmap(scaled)

        # 5. 다음 컷으로 진행
        self.current_shot_idx += 1
        self.current_countdown_display = 0
        QTimer.singleShot(1000, self.prepare_next_shot)

if __name__ == "__main__":
    # 🔥 PyQt6용 DPI 스케일링 정책 (윈도우 대응)
    if hasattr(Qt, 'HighDpiScaleFactorRoundingPolicy'):
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    
    app = QApplication(sys.argv)
    kiosk = KioskMain()
    kiosk.show()
    sys.exit(app.exec())


def on_source_click(self, i):
    """사진 그리드 클릭 처리 (중복 선택 가능)"""
    print(f"[DEBUG] 클릭된 사진 인덱스: {i}")  # 🔥 디버그 출력
    print(f"[DEBUG] 현재 선택 상태: {self.selected_indices}")  # 🔥 디버그 출력
    
    # 빈 슬롯 찾기
    if None not in self.selected_indices:
        print("[DEBUG] 모든 슬롯이 차있음")
        return
    
    # 첫 번째 빈 슬롯에 추가
    idx = self.selected_indices.index(None)
    self.selected_indices[idx] = i
    print(f"[DEBUG] 업데이트 후: {self.selected_indices}")  # 🔥 디버그 출력
    
    self.load_select_page()



