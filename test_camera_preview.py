"""
카메라 프리뷰 테스트
어느 카메라가 캡처보드인지 확인하기 위한 도구
"""

import cv2
import sys

def test_camera(index):
    """
    특정 인덱스의 카메라 영상을 화면에 표시
    """
    print(f"\n{'='*60}")
    print(f"카메라 #{index} 테스트 중...")
    print(f"{'='*60}\n")
    
    # 카메라 열기
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    
    if not cap.isOpened():
        print(f"❌ 카메라 #{index}를 열 수 없습니다.")
        return False
    
    # 카메라 정보
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    
    print(f"✅ 카메라 #{index} 연결됨")
    print(f"해상도: {width} x {height}")
    print(f"FPS: {fps}")
    print(f"\n📺 프리뷰 창이 열립니다...")
    print(f"💡 Canon R100 화면이 보이면 이게 캡처보드입니다!")
    print(f"⌨️  'q' 키를 누르면 종료\n")
    
    window_name = f"Camera #{index} Preview"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    
    frame_count = 0
    
    while True:
        ret, frame = cap.read()
        
        if not ret:
            print(f"⚠️ 프레임 읽기 실패")
            break
        
        frame_count += 1
        
        # 프레임에 정보 표시
        text = f"Camera #{index} | {width}x{height} | Frame: {frame_count}"
        cv2.putText(frame, text, (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        
        # 화면 표시
        cv2.imshow(window_name, frame)
        
        # 'q' 키로 종료
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    cap.release()
    cv2.destroyAllWindows()
    
    print(f"\n✅ 카메라 #{index} 테스트 완료")
    return True


def main():
    print("\n🎥 카메라 프리뷰 테스트")
    print("\n감지된 카메라:")
    print("  카메라 #0: 1280 x 720")
    print("  카메라 #1: 640 x 480")
    
    print("\n어느 카메라를 테스트하시겠어요?")
    
    try:
        index = int(input("카메라 번호 입력 (0 또는 1): ").strip())
        
        if index not in [0, 1]:
            print("❌ 0 또는 1을 입력하세요.")
            return
        
        test_camera(index)
        
        print("\n" + "="*60)
        print("💡 Canon R100 화면이 보였나요?")
        print("   YES → 이 카메라 인덱스를 기록하세요!")
        print("   NO  → 다른 카메라를 테스트하세요")
        print("="*60)
        
    except ValueError:
        print("❌ 숫자를 입력하세요.")
    except KeyboardInterrupt:
        print("\n\n👋 테스트 중단")


if __name__ == "__main__":
    main()