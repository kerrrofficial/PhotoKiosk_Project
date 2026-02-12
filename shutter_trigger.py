"""
EOS Utility 원격 촬영 자동 트리거 (간단 버전)
pywin32 없이 pyautogui만 사용
"""

import time
import pyautogui
from typing import Optional


class EOSRemoteShutter:
    """
    EOS Utility 원격 촬영 창을 제어하여 자동 촬영
    """
    
    def trigger(self, wait_after: float = 0.5) -> bool:
        """
        촬영 트리거 (Space 키 전송)
        
        Args:
            wait_after: 촬영 후 대기 시간 (초)
            
        Returns:
            성공 여부
        """
        print("[EOS] 📸 셔터 트리거!")
        
        # Space 키 전송 (촬영 단축키)
        pyautogui.press('space')
        
        # 짧은 대기 (카메라 응답 시간)
        time.sleep(wait_after)
        
        return True
    
    def check_connection(self) -> bool:
        """
        항상 True 반환 (간단 버전)
        """
        print("[EOS] ⚠️ EOS Utility 원격 라이브 뷰 창이 열려있는지 확인하세요!")
        return True


# 테스트 코드
def test_single_shot():
    """단일 촬영 테스트"""
    print("\n" + "="*60)
    print("EOS Utility 자동 촬영 테스트")
    print("="*60)
    
    shutter = EOSRemoteShutter()
    
    print("\n⚠️ 중요:")
    print("  1. EOS Utility 실행 중")
    print("  2. 원격 라이브 뷰 창 열려있음")
    print("  3. 원격 라이브 뷰 창이 '활성화'되어 있어야 함 (클릭해서 포커스)")
    print("\n3초 후 자동 촬영을 시작합니다...")
    time.sleep(3)
    
    # 촬영
    if shutter.trigger():
        print("✅ Space 키 전송 완료!")
        print("\nincoming_photos/ 폴더를 확인하세요.")
    else:
        print("❌ 촬영 실패")


def test_multiple_shots(count: int = 4):
    """연속 촬영 테스트"""
    print("\n" + "="*60)
    print(f"EOS Utility 연속 촬영 테스트 ({count}장)")
    print("="*60)
    
    shutter = EOSRemoteShutter()
    
    print("\n⚠️ 중요:")
    print("  1. EOS Utility 실행 중")
    print("  2. 원격 라이브 뷰 창 열려있음")
    print("  3. 원격 라이브 뷰 창이 '활성화'되어 있어야 함")
    print(f"\n3초 후 {count}장을 연속 촬영합니다...")
    time.sleep(3)
    
    for i in range(count):
        print(f"\n[{i+1}/{count}] 촬영 중...")
        
        if shutter.trigger(wait_after=2.0):
            print(f"  ✅ 촬영 완료!")
        else:
            print(f"  ❌ 촬영 실패")
        
        if i < count - 1:
            print("  ⏳ 다음 촬영 준비 중...")
            time.sleep(1.0)
    
    print("\n" + "="*60)
    print(f"촬영 완료!")
    print("="*60)
    print("\nincoming_photos/ 폴더를 확인하세요.")


if __name__ == "__main__":
    print("\n🎯 EOS Utility 원격 촬영 자동화 테스트")
    print("\n옵션:")
    print("  1) 단일 촬영 테스트 (1장)")
    print("  2) 연속 촬영 테스트 (4장)")
    print("  3) 연속 촬영 테스트 (8장)")
    
    choice = input("\n선택 (1-3): ").strip()
    
    if choice == "1":
        test_single_shot()
    elif choice == "2":
        test_multiple_shots(4)
    elif choice == "3":
        test_multiple_shots(8)
    else:
        print("❌ 잘못된 선택")