import os
from PIL import Image, ImageOps, ImageFilter
import qrcode
from datetime import datetime

# =========================================================
# [프레임 레이아웃 좌표 설정] (Canvas: 2400 x 3600 px 기준)
# "x, y, w, h" = 사진이 들어갈 위치와 크기
# =========================================================
FRAME_LAYOUTS = {
    # -----------------------------------------------------
    # [1. 하프컷 (Half)] - 2x6인치 2장 (좌우 대칭 복사)
    # 아래 좌표는 왼쪽 스트립(0~1200px) 기준입니다.
    # -----------------------------------------------------
    # 세로형 (Vertical)
    "half_v2": [
        {"x": 50, "y": 44,  "w": 1100, "h": 1600},
        {"x": 50, "y": 1648, "w": 1100, "h": 1600},
        {"x": 1252, "y": 44,  "w": 1100, "h": 1600},
        {"x": 1252, "y": 1648, "w": 1100, "h": 1600}
    ],
    "half_v3": [
        {"x": 50, "y": 50,  "w": 1100, "h": 1100},
        {"x": 50, "y": 1155, "w": 1100, "h": 1100},
        {"x": 50, "y": 2258, "w": 1100, "h": 1100},
        {"x": 1248, "y": 50,  "w": 1100, "h": 1100},
        {"x": 1248, "y": 1155, "w": 1100, "h": 1100},
        {"x": 1248, "y": 2258, "w": 1100, "h": 1100}
    ],
    "half_v4": [ # 인생네컷 국룰
        {"x": 45, "y": 60,  "w": 1110, "h": 800},
        {"x": 45, "y": 880,  "w": 1110, "h": 800},
        {"x": 45, "y": 1700, "w": 1110, "h": 800},
        {"x": 45, "y": 2516, "w": 1110, "h": 800},
        {"x": 1254, "y": 60,  "w": 1110, "h": 800},
        {"x": 1254, "y": 880,  "w": 1110, "h": 800},
        {"x": 1254, "y": 1700, "w": 1110, "h": 800},
        {"x": 1254, "y": 2516, "w": 1110, "h": 800}
    ],
    # 가로형 (Horizontal) - 좁고 긴 사진
    "half_h2": [
        {"x": 60, "y": 85,  "w": 1500, "h": 1050},
        {"x": 1590, "y": 85, "w": 1500, "h": 1050},
        {"x": 60, "y": 1276,  "w": 1500, "h": 1050},
        {"x": 1590, "y": 1276, "w": 1500, "h": 1050}
    ],
    "half_h3": [
        {"x": 101, "y": 50,  "w": 1100, "h": 1100},
        {"x": 1250, "y": 50, "w": 1100, "h": 1100},
        {"x": 2400, "y": 50, "w": 1100, "h": 1100},
        {"x": 101, "y": 1250,  "w": 1100, "h": 1100},
        {"x": 1250, "y": 1250, "w": 1100, "h": 1100},
        {"x": 2400, "y": 1250, "w": 1100, "h": 1100}
    ],
    "half_h4": [
        {"x": 150, "y": 150,  "w": 900, "h": 750},
        {"x": 150, "y": 1000, "w": 900, "h": 750},
        {"x": 150, "y": 1850, "w": 900, "h": 750},
        {"x": 150, "y": 2700, "w": 900, "h": 750}
    ],

    # -----------------------------------------------------
    # [2. 풀컷 (Full)] - 4x6인치 1장
    # -----------------------------------------------------
    # 세로형 (Vertical)
    "full_v1": [
        {
            "x": 40,    
            "y": 410,   
            "w": 2320,  # width -> w 로 변경
            "h": 2320   # height -> h 로 변경
        }
    ],
    "full_v2": [
        {"x": 100, "y": 296,  "w": 2200, "h": 1500},
        {"x": 100, "y": 1800, "w": 2200, "h": 1500},
    ],
    "full_v4a": [ # 정방형 2x2
        {"x": 60,  "y": 546,  "w": 1140, "h": 1140}, # 좌상
        {"x": 1200, "y": 546,  "w": 1140, "h": 1140}, # 우상
        {"x": 60,  "y": 1690, "w": 1140, "h": 1140}, # 좌하
        {"x": 1200, "y": 1690, "w": 1140, "h": 1140}  # 우하
    ],
    "full_v4b": [ # 직사각형 2x2
        {"x": 60,  "y": 68,  "w": 1140, "h": 1560},
        {"x": 1200, "y": 68,  "w": 1140, "h": 1560},
        {"x": 60,  "y": 1638, "w": 1140, "h": 1560},
        {"x": 1200, "y": 1638, "w": 1140, "h": 1560}
    ],
    "full_v9": [ # 3x3
        {"x": 81, "y": 81, "w": 714, "h": 1004}, {"x": 843, "y": 81, "w": 714, "h": 1004}, {"x": 1605, "y": 81, "w": 714, "h": 1004},
        {"x": 81, "y": 1131, "w": 714, "h": 1004}, {"x": 843, "y": 1131, "w": 714, "h": 1004}, {"x": 1605, "y": 1131, "w": 714, "h": 1004},
        {"x": 81, "y": 2183, "w": 714, "h": 1004}, {"x": 850, "y": 2300, "w": 714, "h": 1004}, {"x": 1600, "y": 2300, "w": 714, "h": 1004}
    ],
    
    # 가로형 (Horizontal)
    "full_h2": [ # 위아래로 넓게
        {"x": 70, "y": 62,  "w": 1560, "h": 2280},
        {"x": 1640, "y": 62, "w": 1560, "h": 2280}
    ],
    "full_h4": [ # 가로로 긴 4컷
        {"x": 50, "y": 132, "w": 1500, "h": 1060},
        {"x": 1580, "y": 132, "w": 1500, "h": 1060},
        {"x": 50, "y": 1210, "w": 1500, "h": 1060},
        {"x": 1580, "y": 1210, "w": 1500, "h": 1060}
    ],
    "full_h5": [ # 1(큰거) + 4(작은거)
        {"x": 100, "y": 100,  "w": 2200, "h": 1400}, # 상단 큰거
        {"x": 100,  "y": 1600, "w": 1050, "h": 900}, # 하단 4개
        {"x": 1250, "y": 1600, "w": 1050, "h": 900},
        {"x": 100,  "y": 2600, "w": 1050, "h": 900},
        {"x": 1250, "y": 2600, "w": 1050, "h": 900}
    ],
    "full_h10": [ # 2x5
        {"x": 100, "y": 100,  "w": 1050, "h": 600}, {"x": 1250, "y": 100,  "w": 1050, "h": 600},
        {"x": 100, "y": 800,  "w": 1050, "h": 600}, {"x": 1250, "y": 800,  "w": 1050, "h": 600},
        {"x": 100, "y": 1500, "w": 1050, "h": 600}, {"x": 1250, "y": 1500, "w": 1050, "h": 600},
        {"x": 100, "y": 2200, "w": 1050, "h": 600}, {"x": 1250, "y": 2200, "w": 1050, "h": 600},
        {"x": 100, "y": 2900, "w": 1050, "h": 600}, {"x": 1250, "y": 2900, "w": 1050, "h": 600}
    ],

    # [3. A4] (기존 유지)
    "a4_4cut": [ 
        {"x": 100, "y": 100, "w": 1000, "h": 1500}, {"x": 1300, "y": 100, "w": 1000, "h": 1500},
        {"x": 100, "y": 1700, "w": 1000, "h": 1500}, {"x": 1300, "y": 1700, "w": 1000, "h": 1500}
    ]
}

def merge_4cut_vertical(image_paths, frame_path=None, layout_key="full_4cut"):
    """
    layout_key (예: 'full_v4a', 'half_v3')에 따라 사진을 배치하고 프레임을 합성
    """
    # 가로형 레이아웃은 캔버스를 가로로 생성
    horizontal_layouts = ['h2', 'h4', 'h5', 'h10']
    is_horizontal = any(layout_key.endswith(h) for h in horizontal_layouts)
    
    if is_horizontal:
        CANVAS_W, CANVAS_H = 3600, 2400
    else:
        CANVAS_W, CANVAS_H = 2400, 3600
    
    print(f"[photo_utils] 캔버스: {CANVAS_W}x{CANVAS_H} ({'가로형' if is_horizontal else '세로형'})")
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), "white")
    
    # 레이아웃 정보 가져오기
    layout_data = FRAME_LAYOUTS.get(layout_key)
    if not layout_data:
        print(f"⚠️ 레이아웃 정보 없음 ({layout_key}). 기본 full_v4a 사용.")
        layout_data = FRAME_LAYOUTS["full_v4a"]

    # --- 1. 사진 배치 ---
    for idx, coords in enumerate(layout_data):
        # 슬롯 수만큼 이미지가 있으면 1:1 배치, 부족하면 반복
        img_index = idx % len(image_paths)
        
        if img_index < len(image_paths):
            img_path = image_paths[img_index]
            x, y, w, h = coords['x'], coords['y'], coords['w'], coords['h']
            
            try:
                img = Image.open(img_path)
                img = ImageOps.fit(img, (w, h), centering=(0.5, 0.5))
                canvas.paste(img, (x, y))
                
                pass  # 하프컷도 풀컷과 동일하게 처리
                    
            except Exception as e:
                print(f"이미지 배치 오류 ({img_path}): {e}")

    # --- 2. 프레임 합성 ---
    if frame_path and os.path.exists(frame_path):
        try:
            frame_img = Image.open(frame_path).convert("RGBA")
            frame_img = frame_img.resize((CANVAS_W, CANVAS_H), Image.Resampling.LANCZOS)
            canvas.paste(frame_img, (0, 0), mask=frame_img)
        except Exception as e:
            print(f"프레임 합성 오류: {e}")

    # --- 3. 저장 ---
    save_dir = os.path.join("data", "results")
    os.makedirs(save_dir, exist_ok=True)
    filename = f"print_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    full_path = os.path.join(save_dir, filename)
    canvas.save(full_path, quality=95)
    
    return full_path

def apply_filter(image_path, mode):
    if mode == 'original': return image_path
    try:
        img = Image.open(image_path)
        if mode == 'gray': img = img.convert('L')
        elif mode == 'beauty': img = img.filter(ImageFilter.SMOOTH_MORE)
        elif mode == 'warm':
            r, g, b = img.split(); r = r.point(lambda i: i * 1.1); img = Image.merge('RGB', (r, g, b))
        elif mode == 'cool':
            r, g, b = img.split(); b = b.point(lambda i: i * 1.1); img = Image.merge('RGB', (r, g, b))
        elif mode == 'bright': img = img.point(lambda i: i * 1.2)
        save_path = image_path.replace(".jpg", f"_{mode}.jpg")
        img.save(save_path)
        return save_path
    except: return image_path

def add_qr_to_image(image_path, url="https://example.com"):
    try:
        img = Image.open(image_path)
        qr = qrcode.make(url)
        qr_size = int(img.width * 0.08)
        qr = qr.resize((qr_size, qr_size))
        img.paste(qr, (img.width - qr_size - 50, img.height - qr_size - 50))
        img.save(image_path)
    except: pass

def merge_half_cut(image_paths, frame_path=None, layout_key="half_v4"):
    """
    하프컷 전용 합성 함수
    풀컷과 동일하게 합성 후 좌(0~1200) / 우(1200~2400) 두 장으로 분리 저장
    """
    # 풀컷과 동일하게 합성
    full_path = merge_4cut_vertical(image_paths, frame_path, layout_key)
    
    save_dir = os.path.join("data", "results")
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    full_img = Image.open(full_path)
    
    # 좌측 (0~1200)
    left_img = full_img.crop((0, 0, 1200, 3600))
    left_path = os.path.join(save_dir, f"half_left_{timestamp}.jpg")
    left_img.save(left_path, quality=95)
    
    # 우측 (1200~2400)
    right_img = full_img.crop((1200, 0, 2400, 3600))
    right_path = os.path.join(save_dir, f"half_right_{timestamp}.jpg")
    right_img.save(right_path, quality=95)
    
    print(f"[하프컷] 좌측: {left_path}")
    print(f"[하프컷] 우측: {right_path}")
    
    return left_path, right_path