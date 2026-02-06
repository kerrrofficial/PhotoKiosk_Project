import sys
import os
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
from PyQt6.QtGui import QPixmap, QIcon, QPainter, QColor, QPen, QPageSize, QKeySequence, QShortcut, QImage, QFont, QFontDatabase, QKeyEvent, QScreen, QPainterPath
from PyQt6.QtPrintSupport import QPrinter

# [모듈 import]
# 같은 폴더에 camera_thread.py, photo_utils.py, widgets.py, constants.py 가 있어야 합니다.
from camera_thread import VideoThread
from photo_utils import merge_4cut_vertical, apply_filter, add_qr_to_image, FRAME_LAYOUTS
from widgets import ClickableLabel, BackArrowWidget, CircleButton, GradientButton, QRCheckWidget, GlobalTimerWidget, PaymentPopup
from constants import LAYOUT_OPTIONS_MASTER

class KioskMain(QMainWindow):
    
    def __init__(self):
        super().__init__()
        
        # 0. 디자인 기준 해상도 (16:9)
        self.DESIGN_W = 1920.0
        self.DESIGN_H = 1080.0

        # 현재 화면 추적용
        self.last_screen = None

        # 1. 기본 설정
        self.base_path = os.getcwd()
        self.asset_root = os.path.join(self.base_path, "assets", "frames")
        self.click_count = 0 
        self.session_data = {}
        self.selected_indices = []
        self.captured_files = [] # 촬영된 파일 리스트 초기화
        
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
            'use_filter_page': True, 'save_raw_files': False
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

    # -----------------------------------------------------------
    # [Config & Setup]
    # -----------------------------------------------------------
    def load_event_config(self):
        try:
            path = os.path.join(self.base_path, "event_config.json")
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f: return json.load(f)
        except: pass
        return { "event_name": "Default", "papers": { "full": {"v2": ["*"]} } }

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
    # [Helper Methods] - 스케일링 함수 (s)
    # -----------------------------------------------------------
    def s(self, size):
        """ 1920x1080 기준 픽셀 값을 현재 비율에 맞춰 변환 """
        return int(size * self.scale_factor)

    def create_header(self, parent_layout, title_text, sub_text="", show_back=True, back_callback=None):
        header_widget = QWidget()
        header_height = self.s(260)
        header_widget.setFixedHeight(header_height)
        header_widget.setStyleSheet("background: transparent;")
        
         # 🔥 타이틀/서브타이틀을 화면 전체 너비 기준 중앙 정렬
        title_box = QWidget(header_widget)
        title_box.setGeometry(0, 0, int(self.new_w), header_height)
        
        lbl_title = QLabel(title_text, title_box)
        lbl_title.setStyleSheet(f"font-family: 'TikTok Sans'; font-size: {self.s(40)}pt; font-weight: 600; color: black; background: transparent;")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_title.setGeometry(0, self.s(130), int(self.new_w), self.s(60))
        
        if sub_text:
            lbl_sub = QLabel(sub_text, title_box)
            lbl_sub.setStyleSheet(f"font-family: 'Pretendard'; font-size: {self.s(28)}pt; font-weight: 500; color: #555; background: transparent;")
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
        lbl_t.setStyleSheet(f"font-family: 'Pretendard'; font-size: {self.s(26)}pt; font-weight: 600; color: #828282; border: none; background: transparent;")
        lbl_t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        lbl_n = QLabel("")
        lbl_n.setStyleSheet(f"font-family: 'TikTok Sans'; font-size: {self.s(56)}pt; font-weight: 500; color: black; border: none; background: transparent;")
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
        lbl.setStyleSheet(f"color: #C2C2C2; font-family: 'Pretendard'; font-size: {self.s(24)}pt; font-weight: 600; line-height: 120%; border: none; background: transparent;")
        
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
        page = QWidget(); self.apply_window_style(page, "common")
        main_layout = QVBoxLayout(page)
        main_layout.setContentsMargins(0, 0, 0, self.s(50))
        main_layout.setSpacing(self.s(20))
        self.lbl_timer_frame = self.create_header(main_layout, "Choose Your Frame", "프레임 디자인을 선택해주세요", True, lambda: self.show_page(0))
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")
        self.frame_grid_widget = QWidget(); self.frame_grid_widget.setStyleSheet("background: transparent;")
        self.frame_grid = QGridLayout(self.frame_grid_widget)
        self.frame_grid.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.frame_grid.setContentsMargins(self.s(50), 0, self.s(50), self.s(50))
        self.frame_grid.setSpacing(self.s(30))
        self.scroll_area.setWidget(self.frame_grid_widget)
        main_layout.addWidget(self.scroll_area)
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
            lbl.setStyleSheet(f"background-color: #E3E3E3; border: none; border-radius: {self.s(20)}px; font-family: 'Pretendard'; font-size: {self.s(56)}px; font-weight: 600; color: black;")
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
        self.btn_close_cp.setStyleSheet(f"font-size: {self.s(24)}px; font-weight: bold; background: transparent; color: #999; border: none;")
        cl = QVBoxLayout(self.coupon_widget); cl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.input_coupon = QLineEdit(); self.input_coupon.setFixedSize(self.s(400), self.s(80)); self.input_coupon.setAlignment(Qt.AlignmentFlag.AlignCenter); self.input_coupon.setStyleSheet(f"font-size: {self.s(30)}px; border-radius: {self.s(10)}px; border: 2px solid #ccc;")
        cl.addWidget(self.input_coupon)
        kp = QWidget(); kl = QGridLayout(kp); kl.setSpacing(self.s(10))
        for i, k in enumerate(['1','2','3','4','5','6','7','8','9','C','0','OK']):
            b = QPushButton(k); b.setFixedSize(self.s(80), self.s(80))
            b.setStyleSheet(f"font-size: {self.s(30)}px; font-weight: bold; border-radius: {self.s(10)}px; background-color: {'#ffccdd' if k=='OK' else 'white'}; border: 1px solid #999;")
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
            font-family: 'TikTok Sans';
            font-size: {self.s(56)}pt;
            font-weight: bold;
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
            font-family: 'TikTok Sans';
            font-size: {self.s(40)}pt;
            font-weight: bold;
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
        
        # 좌측: 프레임 미리보기 배경
        preview_bg = QWidget(content_widget)
        preview_bg.setFixedSize(self.s(700), self.s(700))
        preview_bg.setStyleSheet(f"""
            background-color: #ECECEC;
            border-radius: {self.s(12)}px;
        """)
        preview_bg.move(self.s(110), self.s(30))
        
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
        
        # 🔥 비율에 따라 행/열 결정

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
            grid_rows = 3  # 3행이지만 12개만 표시
            print(f"[DEBUG] 정방형 그리드 선택: 5열 x 3행 (0.9 ≤ {hole_ratio:.3f} ≤ 1.1)")

        # 우측: 촬영 사진 그리드
        grid_container = QWidget(content_widget)
        grid_container.setStyleSheet("background: transparent;")

        # 🔥 그리드 영역 계산
        # 좌측: 프레임 미리보기 배경 우측 + 30px
        # 미리보기 위치: x=110, width=700 → 우측 끝 = 810
        grid_x = self.s(110 + 700 + 30)

        # 우측: 타이머와 우측 정렬
        # 타이머 위치: 우측에서 110 + 200
        grid_right = int(self.new_w) - self.s(110)
        grid_width = grid_right - grid_x

        # 🔥 상단: 프레임 미리보기와 상단 정렬
        # 미리보기 배경 y위치: 30
        grid_y = self.s(30)

        # 🔥 하단: 선택완료 버튼보다 30px 위
        # 버튼 y위치: 30 + 700 - 140 = 590
        grid_bottom = self.s(30 + 700 - 140 - 30)
        grid_height = grid_bottom - grid_y

        print(f"[DEBUG] 그리드 영역: x={grid_x}, y={grid_y}, w={grid_width}, h={grid_height}")

        # 그리드 컨테이너 배치 (절대 위치)
        grid_container.setGeometry(grid_x, grid_y, grid_width, grid_height)

        # QGridLayout을 직접 grid_container에 설정
        self.photo_grid = QGridLayout(grid_container)
        self.photo_grid.setSpacing(0)  # 🔥 간격 0
        self.photo_grid.setContentsMargins(0, 0, 0, 0)  # 🔥 여백 0
        self.photo_buttons = []

        # 동적으로 12개 버튼 배치
        for i in range(12):
            b = QPushButton()
            b.setStyleSheet(f"""
                QPushButton {{
                    border: {self.s(2)}px solid #A8A8A8;
                    background-color: white;
                    padding: 0px;
                    margin: 0px;
                }}
                QPushButton:hover {{
                    border: {self.s(2)}px solid #888888;
                }}
                QPushButton:pressed {{
                    background-color: #f0f0f0;
                }}
            """)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            b.clicked.connect(lambda checked=False, x=i: self.on_source_click(x))
            self.photo_buttons.append(b)
            
            # 행/열 계산
            row = i // grid_cols
            col = i % grid_cols
            self.photo_grid.addWidget(b, row, col)
        
        # 선택 완료 버튼
        self.btn_finish_select = GradientButton("선택 완료", "Complete", content_widget, self.s)
        btn_x = int(self.new_w) - self.s(110) - self.s(350)
        btn_y = self.s(30 + 700 - 140)
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
                    pt.setFont(QFont("Arial", self.s(100), QFont.Weight.Bold))
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
        page = QWidget(); self.apply_window_style(page, "common"); main_layout = QHBoxLayout(page); main_layout.setContentsMargins(self.s(50), self.s(50), self.s(50), self.s(50))
        self.result_label = QLabel("이미지 생성 중..."); self.result_label.setAlignment(Qt.AlignmentFlag.AlignCenter); self.result_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding); self.result_label.setStyleSheet("background: white; border: 5px solid white; border-radius: 10px;")
        right_panel = QVBoxLayout()
        lbl = QLabel("필터 선택"); lbl.setAlignment(Qt.AlignmentFlag.AlignCenter); lbl.setStyleSheet(f"font-size: {self.s(55)}px; font-weight: 600; margin-bottom: {self.s(30)}px;")
        right_panel.addWidget(lbl)
        filter_grid = QGridLayout()
        fs = [("원본", "original"), ("🖤 흑백", "gray"), ("✨ 뽀샤시", "beauty"), ("🧡 웜톤", "warm"), ("💙 쿨톤", "cool"), ("☀️ 밝게", "bright")]
        for i, (t, m) in enumerate(fs):
            b = QPushButton(t); b.setFixedSize(self.s(220), self.s(120)); b.clicked.connect(lambda _, x=m: self.apply_filter_click(x)); filter_grid.addWidget(b, i//2, i%2)
        right_panel.addLayout(filter_grid); right_panel.addStretch(1)
        bp = QPushButton("🖨️ 출력 하기"); bp.setFixedHeight(self.s(120)); bp.setStyleSheet(f"background: #3b5998; color: white; font-size: {self.s(50)}px; font-weight: 600; border-radius: {self.s(20)}px;")
        bp.clicked.connect(self.start_printing)
        right_panel.addWidget(bp)
        r_widget = QWidget(); r_widget.setLayout(right_panel); r_widget.setFixedWidth(self.s(500))
        main_layout.addWidget(self.result_label); main_layout.addWidget(r_widget)
        return page

    def apply_filter_click(self, m):
        self.final_print_path = apply_filter(self.final_image_path, m)
        self.result_label.setPixmap(QPixmap(self.final_print_path).scaled(800,1200, Qt.AspectRatioMode.KeepAspectRatio))

    def create_printing_page(self):
        page = QWidget(); self.apply_window_style(page, "print")
        layout = QVBoxLayout(page); layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t = QLabel("Print"); t.setStyleSheet(f"font-size: {self.s(110)}px; font-weight: 600;")
        s = QLabel("잠시만 기다려주세요"); s.setStyleSheet(f"font-size: {self.s(65)}px; font-weight: 600;")
        self.lbl_print_preview = QLabel(); self.lbl_print_preview.setFixedSize(self.s(500), self.s(750)); self.lbl_print_preview.setStyleSheet("border: 5px solid white; border-radius: 20px; background: #ccc;"); self.lbl_print_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(t, alignment=Qt.AlignmentFlag.AlignCenter); layout.addWidget(s, alignment=Qt.AlignmentFlag.AlignCenter); layout.addSpacing(self.s(50)); layout.addWidget(self.lbl_print_preview, alignment=Qt.AlignmentFlag.AlignCenter)
        return page

    def create_admin_page(self):
        page = QWidget(); page.setStyleSheet("background: #F0F0F0;")
        layout = QVBoxLayout(page); layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl = QLabel("🔧 관리자 설정"); lbl.setStyleSheet(f"font-size: {self.s(80)}px; font-weight: 600; color: #333;")
        layout.addWidget(lbl)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFixedSize(self.s(1600), self.s(800))
        panel = QWidget(); panel.setStyleSheet("background: white; border-radius: 20px;")
        self.admin_layout = QVBoxLayout(panel); self.admin_layout.setContentsMargins(40,40,40,40); self.admin_layout.setSpacing(15)
        
        def add_row(t, k, min_v, max_v, step=1):
            r = QWidget(); h = QHBoxLayout(r); 
            l = QLabel(t); l.setFixedWidth(self.s(400)); l.setStyleSheet(f"font-size: {self.s(32)}px; font-weight: 600; color: black;")
            v = QLabel(str(self.admin_settings.get(k))); v.setFixedWidth(self.s(100)); v.setStyleSheet(f"font-size: {self.s(32)}px; color: blue;")
            b1 = QPushButton("-"); b1.setFixedSize(self.s(60),self.s(60))
            b2 = QPushButton("+"); b2.setFixedSize(self.s(60),self.s(60))
            def upd(d):
                current_val = int(v.text())
                new_val = current_val + d
                if min_v <= new_val <= max_v:
                    v.setText(str(new_val))
                    self.admin_settings[k] = new_val
            b1.clicked.connect(lambda: upd(-step))
            b2.clicked.connect(lambda: upd(step))
            h.addWidget(l); h.addWidget(b1); h.addWidget(v); h.addWidget(b2)
            self.admin_layout.addWidget(r)
        
        def add_tog(t, k):
            r = QWidget(); h = QHBoxLayout(r); l = QLabel(t); l.setFixedWidth(self.s(400)); l.setStyleSheet(f"font-size: {self.s(32)}px; font-weight: 600; color: black;")
            s = self.admin_settings.get(k); b = QPushButton("ON" if s else "OFF"); b.setFixedSize(self.s(150), self.s(60)); 
            b.setStyleSheet(f"font-size: {self.s(30)}px; color: white; background-color: {'#4CAF50' if s else '#F44336'}; border-radius: 10px;")
            def tog(): 
                n = 0 if b.text()=="ON" else 1; self.admin_settings[k]=n
                b.setText("ON" if n else "OFF"); b.setStyleSheet(f"font-size: {self.s(30)}px; color: white; background-color: {'#4CAF50' if n else '#F44336'}; border-radius: 10px;")
            b.clicked.connect(tog); h.addWidget(l); h.addWidget(b); self.admin_layout.addWidget(r)

        def add_cmb(t, k, opts):
            r = QWidget(); h = QHBoxLayout(r); l = QLabel(t); l.setFixedWidth(self.s(400)); l.setStyleSheet(f"font-size: {self.s(32)}px; font-weight: 600; color: black;")
            c = QComboBox(); c.setFixedHeight(self.s(60))
            c.setStyleSheet(f"""
                QComboBox {{
                    font-size: {self.s(30)}px;
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
            
            for kv, vv in opts.items(): c.addItem(vv, kv)
            idx = c.findData(self.admin_settings.get(k)); 
            if idx >= 0: c.setCurrentIndex(idx)
            c.currentIndexChanged.connect(lambda i: self.admin_settings.update({k: c.itemData(i)})); h.addWidget(l); h.addWidget(c); self.admin_layout.addWidget(r)

        l1 = QLabel("기본 설정"); l1.setStyleSheet(f"font-size: {self.s(40)}px; font-weight: 600; margin-top: 20px; color: black;"); self.admin_layout.addWidget(l1)
        add_cmb("결제 방식", "payment_mode", {1: "유상결제 (카드/현금/쿠폰)", 0: "무상결제 (이벤트)", 2: "코인결제 (코인기)"})
        add_row("코인 단가", "coin_price_per_sheet", 1, 10)
        l2 = QLabel("가격 설정"); l2.setStyleSheet(f"font-size: {self.s(40)}px; font-weight: 600; margin-top: 20px; color: black;"); self.admin_layout.addWidget(l2)
        add_row("Full Price", "price_full", 0, 20000, 500); add_row("Half Price", "price_half", 0, 20000, 500)
        add_tog("카드 결제", "use_card"); add_tog("현금 결제", "use_cash"); add_tog("쿠폰 결제", "use_coupon"); add_tog("다크 모드", "use_dark_mode")
        l3 = QLabel("출력 수량 설정 (2의 배수)"); l3.setStyleSheet(f"font-size: {self.s(40)}px; font-weight: 600; margin-top: 20px; color: black;"); self.admin_layout.addWidget(l3)
        add_row("최소 수량 (Min)", "print_count_min", 2, 12, step=2); add_row("최대 수량 (Max)", "print_count_max", 2, 12, step=2)
        l4 = QLabel("촬영 설정"); l4.setStyleSheet(f"font-size: {self.s(40)}px; font-weight: 600; margin-top: 20px; color: black;"); self.admin_layout.addWidget(l4)
        add_row("총 촬영 컷수", "total_shoot_count", 1, 12); add_row("촬영 타이머 (초)", "shot_countdown", 1, 10)
        
        scroll.setWidget(panel); layout.addWidget(scroll)
        ex = QPushButton("나가기 (저장)"); ex.setFixedSize(self.s(500), self.s(100)); ex.setStyleSheet(f"font-size: {self.s(45)}px; background: #ff007f; color: white; border-radius: 20px;")
        ex.clicked.connect(lambda: self.show_page(0)); layout.addWidget(ex)
        return page

    def process_timer_tick(self):
        self.remaining_time -= 1
        idx = self.stack.currentIndex()
        target_lbl = None
        if idx == 1: target_lbl = getattr(self, 'lbl_timer_frame', None)
        elif idx == 2: target_lbl = getattr(self, 'lbl_timer_payment', None)
        elif idx == 4: target_lbl = getattr(self, 'lbl_timer_select', None)  # 🔥 추가
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
        self.payment_timer = QTimer(self); self.payment_timer.setSingleShot(True); self.payment_timer.timeout.connect(lambda: self.on_payment_approved(m)); self.payment_timer.start(3000)
        self.payment_popup_dialog.rejected.connect(self.payment_timer.stop)

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
            if self.frame_grid.itemAt(i).widget(): self.frame_grid.itemAt(i).widget().setParent(None)
        papers = self.event_config.get("papers", {})
        all_frames = []
        for p_type, layouts in papers.items():
            for l_key, files in layouts.items():
                d = os.path.join(self.asset_root, p_type, l_key)
                if not os.path.exists(d): continue
                fs = glob.glob(os.path.join(d, "*.png")) if "*" in files else [os.path.join(d, f) for f in files if os.path.exists(os.path.join(d, f))]
                for fp in fs:
                    if os.path.basename(fp).endswith("_btn.png"): continue
                    bn = os.path.splitext(os.path.basename(fp))[0]
                    btn_p = os.path.join(d, f"{bn}_btn.png")
                    all_frames.append({ "path": fp, "btn_path": btn_p if os.path.exists(btn_p) else fp, "paper": p_type, "layout": l_key, "name": bn })
        
        bs, fs = self.s(300), self.s(20)
        for i, item in enumerate(all_frames):
            c = QWidget(); v = QVBoxLayout(c); v.setContentsMargins(0,0,0,0); v.setSpacing(self.s(10)); v.setAlignment(Qt.AlignmentFlag.AlignCenter)
            b = QPushButton(); b.setFixedSize(bs, bs)
            b.setStyleSheet(f"QPushButton {{ border-image: url('{item['btn_path'].replace(os.sep, '/')}'); border-radius: {self.s(50)}px; border: none; background-color: transparent; }}")
            b.clicked.connect(lambda _, it=item: self.select_frame_and_go(it))
            l = QLabel(item["name"]); l.setAlignment(Qt.AlignmentFlag.AlignCenter); l.setStyleSheet(f"font-family: 'Pretendard'; font-size: {fs}px; color: black; background: transparent;")
            v.addWidget(b); v.addWidget(l)
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
        
        # 2. 천 단위 콤마 및 '원' 단위 표시
        self.lbl_price.setText(f"{total:,}원")

    def update_button_ui(self):
        """버튼 활성화/비활성화 업데이트"""
        current = self.session_data.get('print_qty', 2)
        min_q = self.admin_settings.get('print_count_min', 2)
        max_q = self.admin_settings.get('print_count_max', 12)
        
        self.btn_minus.setEnabled(current > min_q)
        self.btn_plus.setEnabled(current < max_q)

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
        
        # 8. 카운트다운 숫자 그리기
        if hasattr(self, 'current_countdown_display') and self.current_countdown_display > 0:
            font = QFont("Arial", self.s(250), QFont.Weight.Bold)
            painter.setFont(font)
            
            text = str(self.current_countdown_display)
            rect = QRect(0, 0, target_w, target_h)
            
            painter.setPen(QColor(0, 0, 0, 150))
            painter.translate(5, 5)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
            
            painter.setPen(QColor("white"))
            painter.translate(-5, -5)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
            
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
        elif idx==3: self.cam_thread = VideoThread(); self.cam_thread.change_pixmap_signal.connect(self.update_image); self.cam_thread.start(); QTimer.singleShot(1000, self.start_shooting)
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
        elif idx==5: self.final_print_path = self.final_image_path; self.result_label.setPixmap(QPixmap(self.final_image_path).scaled(800,1200, Qt.AspectRatioMode.KeepAspectRatio))
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
            self.timer.start(1000)
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
        
        # 🔥 미리보기창 동적 생성
        # 기존 위젯 제거
        for lbl in self.left_previews + self.right_previews:
            lbl.deleteLater()
        self.left_previews.clear()
        self.right_previews.clear()
        
        # 🔥 좌측 우측 배분: 좌측 우선 (4개까지), 나머지는 우측
        left_count = min(self.total_shots, 4)  # 좌측 최대 4개
        right_count = max(0, self.total_shots - 4)  # 나머지는 우측
        
        # 🔥 공통 스타일 (회색 배경 박스)
        preview_style = f"""
            background-color: #333; 
            border-radius: {self.s(10)}px;
            border: none;
        """
        
        # 🔥 좌측 미리보기 생성
        for i in range(left_count):
            lbl = QLabel()
            lbl.setStyleSheet(preview_style)
            lbl.setScaledContents(False)  # 비율 유지
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.left_layout.addWidget(lbl)
            self.left_previews.append(lbl)
        
        # 좌측 여백
        if left_count < 4:
            self.left_layout.addStretch(4 - left_count)
        
        # 🔥 우측 미리보기 생성
        for i in range(right_count):
            lbl = QLabel()
            lbl.setStyleSheet(preview_style)
            lbl.setScaledContents(False)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.right_layout.addWidget(lbl)
            self.right_previews.append(lbl)
        
        # 우측 여백
        if right_count < 4:
            self.right_layout.addStretch(4 - right_count)
        
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
        
        # 🔥 4. 사이드바 미리보기 업데이트 (구멍 비율에 맞춰)
        all_previews = self.left_previews + self.right_previews
        preview_idx = self.current_shot_idx - 1
        
        if preview_idx < len(all_previews):
            lbl = all_previews[preview_idx]
            pix = QPixmap(filepath)
            
            if slot_info and not pix.isNull():
                # 🔥 구멍 비율 계산
                hole_w = slot_info['w']
                hole_h = slot_info['h']
                hole_ratio = hole_w / hole_h
                
                # 🔥 라벨 크기 가져오기
                label_w = lbl.width()
                label_h = lbl.height()
                
                if label_w <= 0 or label_h <= 0:
                    # 아직 렌더링 안됨 - 기본값 사용
                    label_w = self.s(170)  # 230 - 60(여백)
                    label_h = self.s(170)
                
                label_ratio = label_w / label_h
                
                # 🔥 구멍 비율에 맞춰 표시 크기 계산
                if label_ratio > hole_ratio:
                    # 라벨이 더 넓음 -> 높이 기준
                    display_h = label_h
                    display_w = int(display_h * hole_ratio)
                else:
                    # 라벨이 더 좁음 -> 너비 기준
                    display_w = label_w
                    display_h = int(display_w / hole_ratio)
                
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
                
                # 크롭 후 스케일
                cropped = pix.copy(crop_x, crop_y, crop_w, crop_h)
                scaled = cropped.scaled(
                    display_w, display_h,
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                
                lbl.setPixmap(scaled)
                print(f"[DEBUG] 미리보기 {preview_idx}: 구멍비율 {hole_ratio:.3f} ({hole_w}x{hole_h}), 표시크기 {display_w}x{display_h}")
            else:
                # 구멍 정보 없으면 기본 표시
                scaled_pix = pix.scaled(
                    lbl.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                lbl.setPixmap(scaled_pix)

        # 5. 다음 컷으로 진행
        self.current_shot_idx += 1
        self.current_countdown_display = 0
        QTimer.singleShot(1000, self.prepare_next_shot)

if __name__ == "__main__":
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
