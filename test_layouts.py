from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from photo_utils import merge_4cut_vertical, FRAME_LAYOUTS

# 더미 이미지 생성
dummy_dir = Path("test_photos")
dummy_dir.mkdir(exist_ok=True)

photos = []
for i in range(8):
    img = Image.new('RGB', (6000, 4000), color=(255-i*30, 100+i*15, 50+i*20))
    draw = ImageDraw.Draw(img)
    
    text = f"#{i+1}"
    bbox = draw.textbbox((0, 0), text)
    position = (3000 - (bbox[2]-bbox[0])//2, 2000 - (bbox[3]-bbox[1])//2)
    draw.text(position, text, fill='white')
    
    path = dummy_dir / f"photo_{i+1:02d}.jpg"
    img.save(path, quality=95)
    photos.append(str(path))
    print(f"✅ {path.name}")

# 레이아웃 테스트
for layout_key in ["full_v2", "full_v4a", "half_v4"]:
    result = merge_4cut_vertical(photos, layout_key=layout_key)
    print(f"✅ {layout_key}: {result}")

print("\n결과 확인: data/results/")