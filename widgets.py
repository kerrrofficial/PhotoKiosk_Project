# widgets.py
import platform  # 🔥 추가
from PyQt6.QtWidgets import QWidget, QLabel, QPushButton, QVBoxLayout, QDialog
from PyQt6.QtCore import Qt, QRect, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QPainterPath

# 🔥 공통 폰트 스케일 함수 생성기
def create_font_scale(scale_func):
    """
    위젯용 폰트 스케일 함수 생성
    
    윈도우 기준으로 최적화되어 있으며,
    맥에서는 약간 크게 표시됨
    """
    def font_scale(size):
        scaled = scale_func(size)
        if platform.system() == 'Darwin':  # macOS
            scaled = int(scaled * 1.12)
        return scaled
    return font_scale

class ClickableLabel(QLabel):
    clicked = pyqtSignal(int, int)
    def mousePressEvent(self, event):
        self.clicked.emit(event.pos().x(), event.pos().y())
        super().mousePressEvent(event)

class BackArrowWidget(QWidget):
    def __init__(self, parent=None, color="#C2C2C2", thickness=4):
        super().__init__(parent)
        self.color = QColor(color)
        self.thickness = thickness
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self.color)
        pen.setWidth(self.thickness)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        w, h = self.width(), self.height()
        t = self.thickness / 2
        path = QPainterPath()
        path.moveTo(w - t, t)
        path.lineTo(t, h / 2)
        path.lineTo(w - t, h - t)
        painter.drawPath(path)

class CircleButton(QPushButton):
    def __init__(self, parent=None, is_plus=True, scale_func=None):
        super().__init__(parent)
        self.s = scale_func if scale_func else (lambda x: x)
        self.fs = create_font_scale(self.s)  # 🔥 헬퍼 함수 사용
        self.is_plus = is_plus  # 🔥 누락된 부분 추가
        
        self.setFixedSize(self.s(140), self.s(140))
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(227, 227, 227, 0.8);
                border-radius: {self.s(70)}px;
                border: none; 
            }}
            QPushButton:pressed {{
                background-color: rgba(200, 200, 200, 0.9);
            }}
        """)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        border_pen = QPen(QColor("#5F5F5F"))
        border_pen.setWidth(1) 
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(1, 1, self.width()-2, self.height()-2)
        
        icon_pen = QPen(QColor("black"))
        icon_pen.setWidth(4)
        icon_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(icon_pen)
        
        cx, cy = self.width() / 2, self.height() / 2
        line_len = self.s(60) / 2 
        
        painter.drawLine(int(cx - line_len), int(cy), int(cx + line_len), int(cy))
        if self.is_plus:
            painter.drawLine(int(cx), int(cy - line_len), int(cx), int(cy + line_len))

class GradientButton(QPushButton):
    def __init__(self, main_text, sub_text, parent=None, scale_func=None):
        super().__init__(parent)
        self.s = scale_func if scale_func else (lambda x: x)
        self.fs = create_font_scale(self.s)  # 🔥 헬퍼 함수 사용
        
        self.setFixedSize(self.s(350), self.s(140))
        
        border_width = max(1, self.s(1))
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: qlineargradient(
                    spread:pad, x1:0, y1:1, x2:0, y2:0, 
                    stop:0 #B6B6B6, stop:1 #F0F0F0
                );
                border: {border_width}px solid #787878;
                border-radius: {self.s(70)}px;
            }}
            QPushButton:pressed {{ 
                background-color: #B6B6B6; 
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self.s(5))
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        lbl_main = QLabel(main_text)
        lbl_main.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_main.setStyleSheet(f"""
            color: black; 
            font-family: 'Pretendard Medium'; 
            font-size: {self.fs(36)}pt;
            background: transparent; 
            border: none;
        """)
        
        lbl_sub = QLabel(sub_text)
        lbl_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_sub.setStyleSheet(f"""
            color: #555555; 
            font-family: 'Pretendard Medium'; 
            font-size: {self.fs(26)}pt;
            background: transparent; 
            border: none;
        """)
        
        layout.addWidget(lbl_main)
        layout.addWidget(lbl_sub)

class QRCheckWidget(QWidget):
    def __init__(self, parent=None, scale_func=None):
        super().__init__(parent)
        self.s = scale_func if scale_func else (lambda x: x)
        self.fs = create_font_scale(self.s)  # 🔥 헬퍼 함수 사용
        self.is_checked = True
        
        self.setFixedSize(self.s(600), self.s(80))
        
        # 체크박스 버튼
        self.btn_check = QPushButton(self)
        self.btn_check.setGeometry(0, 0, self.s(60), self.s(60))
        self.btn_check.setCheckable(True)
        self.btn_check.setChecked(True)
        self.btn_check.clicked.connect(self.toggle_state)
        self.btn_check.setStyleSheet("background: transparent; border: none;")

        # 타이틀 라벨
        self.lbl_title = QLabel("QR코드 사용", self)
        self.lbl_title.move(self.s(80), 0)
        self.lbl_title.setStyleSheet(f"""
            font-family: 'Pretendard Medium'; 
            font-size: {self.fs(30)}px; 
            color: black; 
            background: transparent;
        """)
        self.lbl_title.adjustSize()

        # 설명 라벨
        title_bottom = self.lbl_title.y() + self.lbl_title.height()
        self.lbl_desc = QLabel("24시간 동안 사진 / 동영상 다운로드 가능", self)
        self.lbl_desc.move(self.s(80), title_bottom + self.s(5))
        self.lbl_desc.setStyleSheet(f"""
            font-family: 'Pretendard Medium'; 
            font-size: {self.fs(22)}px; 
            color: #858585; 
            background: transparent;
        """)
        self.lbl_desc.adjustSize()
        
        # 전체 클릭 영역
        self.btn_full_click = QPushButton(self)
        self.btn_full_click.setGeometry(0, 0, self.width(), self.height())
        self.btn_full_click.setStyleSheet("background: transparent; border: none;")
        self.btn_full_click.clicked.connect(self.toggle_state)
        self.btn_full_click.lower() 
            
    def toggle_state(self):
        self.is_checked = not self.is_checked
        self.btn_check.setChecked(self.is_checked)
        self.update()

    def isChecked(self):
        return self.is_checked

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        box_size = self.s(60)
        rect = QRect(0, 0, box_size, box_size)
        
        bg_color = QColor(73, 59, 219, int(255 * 0.8))
        if not self.is_checked:
            bg_color = QColor(200, 200, 200, 200)

        painter.setBrush(bg_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, self.s(10), self.s(10))
        
        if self.is_checked:
            painter.setBrush(Qt.BrushStyle.NoBrush) 
            pen = QPen(QColor("white"))
            pen.setWidth(self.s(4))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            
            p1 = (int(box_size * 0.25), int(box_size * 0.50))
            p2 = (int(box_size * 0.45), int(box_size * 0.70))
            p3 = (int(box_size * 0.75), int(box_size * 0.30))
            
            path = QPainterPath()
            path.moveTo(*p1); path.lineTo(*p2); path.lineTo(*p3)
            painter.drawPath(path)

class GlobalTimerWidget(QWidget):
    def __init__(self, parent=None, scale_func=None):
        super().__init__(parent)
        self.s = scale_func if scale_func else (lambda x: x)
        self.fs = create_font_scale(self.s)  # 🔥 헬퍼 함수 사용
        
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True) 
        self.setObjectName("timer_widget")
        self.setFixedSize(self.s(220), self.s(140))
        self.setStyleSheet(f"""
            #timer_widget {{
                background-color: rgba(227, 227, 227, 0.8);
                border: {self.s(1)}px solid #5F5F5F;
                border-radius: {self.s(20)}px;
            }}
        """)
        
        self.lbl_title = QLabel("TIMER", self)
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_title.setGeometry(0, self.s(20), self.width(), self.s(30))
        self.lbl_title.setStyleSheet(f"""
            color: #828282; 
            font-family: 'Pretendard SemiBold'; 
            font-size: {self.fs(24)}px; 
            border: none; 
            background: transparent;
        """)
        
        self.lbl_num = QLabel("", self)
        self.lbl_num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_num.setGeometry(0, self.s(44), self.width(), self.s(80))
        self.lbl_num.setStyleSheet(f"""
            color: #333333; 
            font-family: 'TikTok Sans 16pt SemiBold'; 
            font-size: {self.fs(60)}px; 
            border: none; 
            background: transparent;
        """)

    def set_time(self, seconds):
        self.lbl_num.setText(str(seconds))

class PaymentPopup(QDialog):
    def __init__(self, parent=None, is_dark=False, scale_func=None, mode="card"):
        super().__init__(parent)
        self.s = scale_func if scale_func else (lambda x: x)
        self.fs = create_font_scale(self.s)  # 🔥 헬퍼 함수 사용
        
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setFixedSize(self.s(600), self.s(350))
        
        bg = "black" if is_dark else "white"
        fg = "white" if is_dark else "black"
        border = "white" if is_dark else "#333"
        
        self.setStyleSheet(f"""
            QDialog {{ 
                background-color: {bg}; 
                border: {self.s(5)}px solid {border}; 
                border-radius: {self.s(30)}px; 
            }} 
            QLabel {{ 
                color: {fg}; 
                font-size: {self.fs(30)}pt; 
                font-weight: 600; 
                border: none; 
                font-family: 'Pretendard SemiBold', sans-serif; 
            }}
        """)
        
        self.btn_close = QPushButton("X", self)
        self.btn_close.setGeometry(self.width() - self.s(60), self.s(20), self.s(40), self.s(40))
        self.btn_close.clicked.connect(self.reject)
        self.btn_close.setStyleSheet(f"""
            QPushButton {{ 
                color: #999; 
                font-family: 'Pretendard SemiBold'; 
                font-size: {self.fs(30)}px; 
                font-weight: bold; 
                background: transparent; 
                border: none; 
            }} 
            QPushButton:hover {{ 
                color: red; 
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 모드별 아이콘/메시지
        icon_char, text_msg = "💳", "카드를 꽂아주세요"
        if mode == "cash":
            icon_char, text_msg = "💵", "지폐를 투입구에\n넣어주세요"
        elif mode == "coin":
            icon_char, text_msg = "🪙", "코인을 투입해주세요"
        elif mode == "coupon":
            icon_char, text_msg = "🎫", "쿠폰을 확인 중입니다"
        
        lbl_icon = QLabel(icon_char)
        lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_icon.setStyleSheet(f"""
            font-size: {self.fs(80)}px; 
            margin-bottom: {self.s(20)}px; 
            color: {fg};
        """)
        
        lbl_text = QLabel(text_msg)
        lbl_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        layout.addWidget(lbl_icon)
        layout.addWidget(lbl_text)