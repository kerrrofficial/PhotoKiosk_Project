#!/usr/bin/env python3
"""
카메라 디바이스 확인 스크립트
Canon R100이 몇 번 인덱스로 잡히는지 확인
"""
import cv2
import platform

print("=" * 60)
print(f"OS: {platform.system()} {platform.release()}")
print("=" * 60)

# 0~5번까지 카메라 인덱스 테스트
for i in range(6):
    cap = cv2.VideoCapture(i)
    
    if cap.isOpened():
        # 카메라 정보 가져오기
        width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        fps = cap.get(cv2.CAP_PROP_FPS)
        backend = cap.getBackendName()
        
        print(f"\n✅ 카메라 #{i} 발견!")
        print(f"   - 해상도: {int(width)} x {int(height)}")
        print(f"   - FPS: {fps}")
        print(f"   - Backend: {backend}")
        
        # 프레임 1장 읽어보기
        ret, frame = cap.read()
        if ret:
            print(f"   - 프레임 읽기: 성공")
        else:
            print(f"   - 프레임 읽기: 실패")
        
        cap.release()
    else:
        print(f"❌ 카메라 #{i}: 없음")

print("\n" + "=" * 60)
print("💡 Canon R100이 보이면 해당 인덱스 번호를 기록하세요!")
print("=" * 60)