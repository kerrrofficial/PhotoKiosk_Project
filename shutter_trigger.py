"""
EOS Utility 원격 촬영 자동 트리거
Canon EOS R100 + EOS Utility 전용

사용법:
    from shutter_trigger import EOSRemoteShutter
    
    shutter = EOSRemoteShutter()
    if shutter.trigger():
        print("촬영 성공!")
"""

import time
import win32gui
import win32con
import pyautogui
from typing import Optional


class EOSRemoteShutter:
    """
    EOS Utility 원격 촬영 창을 제어하여 자동 촬영
    """
    
    # EOS Utility 창 제목 (버전/언어에 따라 다를 수 있음)
    WINDOW_TITLES = [
        "EOS R100",           # 메인 창
        "원격 라이브 뷰 창",   # 라이브 뷰 창 (한글)
        "Remote Live View",   # 라이브 뷰 창 (영문)
    ]
    
    def __init__(self):
        self.last_window_handle = None
        
    def find_eos_window(self) -> Optional[int]:
        """
        EOS Utility 관련 창 찾기
        
        Returns:
            창 핸들 (hwnd) 또는 None
        """
        for title in self.WINDOW_TITLES:
            hwnd = win32gui.FindWindow(None, title)
            if hwnd and win32gui.IsWindowVisible(hwnd):
                print(f"[EOS] 창 발견: {title}")
                self.last_window_handle = hwnd
                return hwnd
        
        print("[EOS] ❌ EOS Utility 창을 찾을 수 없습니다.")
        print("[EOS] 확인사항:")
        print("  1. EOS Utility가 실행되어 있나요?")
        print("  2. '원격 라이브 뷰 창'이 열려있나요?")
        return None
    
    def activate_window(self, hwnd: int) -> bool:
        """
        창을 활성화 (포커스)
        
        Args:
            hwnd: 윈도우 핸들
            
        Returns:
            성공 여부
        """
        try:
            # 최소화된 창이면 복원
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.1)
            
            # 창을 맨 앞으로
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.1)
            
            return True
        except Exception as e:
            print(f"[EOS] 창 활성화 실패: {e}")
            return False
    
    def trigger(self, wait_after: float = 0.5, auto_activate: bool = True) -> bool:
        """
        촬영 트리거 (Space 키 전송)
        
        Args:
            wait_after: 촬영 후 대기 시간 (초)
            auto_activate: 자동으로 창 활성화 여부
            
        Returns:
            성공 여부
        """
        # 1. EOS Utility 창 찾기 (auto_activate=True일 때만)
        if auto_activate:
            hwnd = self.find_eos_window()
            
            if hwnd is None:
                print("[EOS] ❌ EOS Utility 창을 찾을 수 없습니다.")
                print("[EOS] 확인사항:")
                print("  1. EOS Utility가 실행되어 있나요?")
                print("  2. '원격 라이브 뷰 창'이 열려있나요?")
                return False
            
            # 2. 창 활성화
            print(f"[EOS] ✅ 창 찾음!")
            self.activate_window(hwnd)
        
        # 3. Space 키 전송 후 즉시 키오스크 창으로 포커스 복귀
        print("[EOS] 📸 셔터 트리거!")
        pyautogui.press('space')
        time.sleep(0.1)
        # 키오스크 창 찾아서 포그라운드로 복귀
        kiosk_titles = ["PhotoKiosk", "Kiosk", "aurapic", "키오스크"]
        for title in kiosk_titles:
            hwnd = win32gui.FindWindow(None, title)
            if not hwnd:
                # 부분 일치로 찾기
                def enum_callback(h, results):
                    if win32gui.IsWindowVisible(h):
                        t = win32gui.GetWindowText(h)
                        if title.lower() in t.lower():
                            results.append(h)
                results = []
                win32gui.EnumWindows(enum_callback, results)
                if results:
                    hwnd = results[0]
            if hwnd:
                try:
                    win32gui.SetForegroundWindow(hwnd)
                except:
                    pass
                break
        
        # 4. 대기
        time.sleep(wait_after)
        
        return True
    
    def check_connection(self) -> bool:
        """
        EOS Utility 연결 상태 확인
        
        Returns:
            창이 열려있으면 True
        """
        hwnd = self.find_eos_window()
        return hwnd is not None


# ============================================================
# 테스트 코드
# ============================================================

def test_single_shot():
    """단일 촬영 테스트"""
    print("\n" + "="*60)
    print("EOS Utility 자동 촬영 테스트")
    print("="*60)
    
    shutter = EOSRemoteShutter()
    
    # 연결 확인
    if not shutter.check_connection():
        print("\n❌ EOS Utility가 실행되지 않았거나 창을 찾을 수 없습니다.")
        return
    
    print("\n✅ EOS Utility 연결됨!")
    print("\n3초 후 자동 촬영을 시작합니다...")
    time.sleep(3)
    
    # 촬영
    if shutter.trigger():
        print("✅ 촬영 완료!")
        print("\nincoming_photos/ 폴더를 확인하세요.")
    else:
        print("❌ 촬영 실패")


def test_multiple_shots(count: int = 4):
    """연속 촬영 테스트"""
    print("\n" + "="*60)
    print(f"EOS Utility 연속 촬영 테스트 ({count}장)")
    print("="*60)
    
    shutter = EOSRemoteShutter()
    
    if not shutter.check_connection():
        print("\n❌ EOS Utility가 실행되지 않았거나 창을 찾을 수 없습니다.")
        return
    
    print("\n✅ EOS Utility 연결됨!")
    print(f"\n3초 후 {count}장을 연속 촬영합니다...")
    time.sleep(3)
    
    success_count = 0
    
    for i in range(count):
        print(f"\n[{i+1}/{count}] 촬영 중...")
        
        if shutter.trigger(wait_after=2.0):  # 촬영 간격 2초
            success_count += 1
            print(f"  ✅ 촬영 완료!")
        else:
            print(f"  ❌ 촬영 실패")
        
        # 마지막 촬영이 아니면 대기
        if i < count - 1:
            print("  ⏳ 다음 촬영 준비 중...")
            time.sleep(1.0)
    
    print("\n" + "="*60)
    print(f"촬영 완료: {success_count}/{count}장 성공")
    print("="*60)
    print("\nincoming_photos/ 폴더를 확인하세요.")


if __name__ == "__main__":
    import sys
    
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