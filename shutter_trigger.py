"""
EOS Utility 원격 촬영 자동 트리거 (개선 버전)
자동으로 원격 라이브 뷰 창 활성화
"""

import time
import pyautogui
pyautogui.FAILSAFE = False  # 키오스크용 필수
import subprocess
from typing import Optional


class EOSRemoteShutter:
    """
    EOS Utility 원격 촬영 창을 제어하여 자동 촬영
    """
    
    # EOS Utility 창 제목 후보들
    WINDOW_TITLES = [
        "원격 라이브 뷰 창",
        "Remote Live View",
        "EOS R100"
    ]
    
    def __init__(self):
        self.last_activated_title = None
    
    def activate_eos_window(self) -> bool:
        """
        EOS Utility 창 활성화 (재시도 포함)
        """
        for attempt in range(3):  # 3회 재시도
            for title in self.WINDOW_TITLES:
                try:
                    cmd = f'''
                    $wshell = New-Object -ComObject wscript.shell;
                    $wshell.AppActivate('{title}')
                    '''
                    result = subprocess.run(
                        ["powershell", "-WindowStyle", "Hidden", "-Command", cmd],
                        capture_output=True,
                        timeout=2
                    )

                    if result.returncode == 0:
                        time.sleep(0.3)
                        self.last_activated_title = title
                        print(f"[EOS] 활성화 성공: {title}")
                        return True
                except:
                    continue

            print(f"[EOS] 활성화 실패 (시도 {attempt+1}/3)")
            time.sleep(0.5)

        print("[EOS] ❌ EOS 창 활성화 완전 실패")
        return False

    
    def trigger(self, wait_after: float = 2.0, auto_activate: bool = True) -> bool:
        """
        촬영 트리거
        """
        if auto_activate:
            if not self.activate_eos_window():
                return False

        try:
            pyautogui.press('space')
            time.sleep(wait_after)
            return True
        except Exception as e:
            print(f"[EOS] 셔터 오류: {e}")
            return False

    
    def check_connection(self) -> bool:
        """
        EOS Utility 연결 상태 확인
        """
        print("[EOS] ⚠️ EOS Utility 원격 라이브 뷰 창이 열려있는지 확인하세요!")
        return True


# ============================================================
# 테스트 코드
# ============================================================

def test_single_shot():
    """단일 촬영 테스트"""
    print("\n" + "="*60)
    print("EOS Utility 자동 촬영 테스트 (개선 버전)")
    print("="*60)
    
    shutter = EOSRemoteShutter()
    
    print("\n✅ 준비사항:")
    print("  1. EOS Utility 실행 중")
    print("  2. 원격 라이브 뷰 창 열려있음")
    print("  3. 자동으로 창을 활성화합니다!")
    
    print("\n3초 후 자동 촬영을 시작합니다...")
    time.sleep(3)
    
    # 촬영 (자동 활성화 ON)
    if shutter.trigger(auto_activate=True):
        print("✅ 촬영 완료!")
        print("\n5초 후 incoming_photos/ 폴더를 확인하세요.")
        time.sleep(5)
    else:
        print("❌ 촬영 실패")


def test_multiple_shots(count: int = 4):
    """연속 촬영 테스트 (개선 버전)"""
    print("\n" + "="*60)
    print(f"EOS Utility 연속 촬영 테스트 ({count}장)")
    print("="*60)
    
    shutter = EOSRemoteShutter()
    
    print("\n✅ 준비사항:")
    print("  1. EOS Utility 실행 중")
    print("  2. 원격 라이브 뷰 창 열려있음")
    print("  3. 자동으로 창을 활성화합니다!")
    
    print(f"\n3초 후 {count}장을 연속 촬영합니다...")
    time.sleep(3)
    
    for i in range(count):
        print(f"\n[{i+1}/{count}] 촬영 중...")
        
        # 매번 창 활성화 + 촬영
        if shutter.trigger(wait_after=3.0, auto_activate=True):
            print(f"  ✅ 촬영 완료!")
        else:
            print(f"  ❌ 촬영 실패")
        
        # 다음 촬영 대기
        if i < count - 1:
            print("  ⏳ 다음 촬영 준비 중...")
            time.sleep(2.0)
    
    print("\n" + "="*60)
    print(f"촬영 완료!")
    print("="*60)
    print("\nincoming_photos/ 폴더를 확인하세요.")


def test_window_activation():
    """창 활성화 테스트"""
    print("\n" + "="*60)
    print("창 활성화 테스트")
    print("="*60)
    
    shutter = EOSRemoteShutter()
    
    print("\n원격 라이브 뷰 창을 찾는 중...")
    
    if shutter.activate_eos_window():
        print("\n✅ 창 활성화 성공!")
        print("원격 라이브 뷰 창이 맨 앞으로 와야 합니다.")
    else:
        print("\n❌ 창 활성화 실패")
        print("원격 라이브 뷰 창이 열려있는지 확인하세요.")


if __name__ == "__main__":
    print("\n🎯 EOS Utility 원격 촬영 자동화 테스트 (개선 버전)")
    print("\n옵션:")
    print("  0) 창 활성화 테스트")
    print("  1) 단일 촬영 테스트 (1장)")
    print("  2) 연속 촬영 테스트 (4장)")
    print("  3) 연속 촬영 테스트 (8장)")
    
    choice = input("\n선택 (0-3): ").strip()
    
    if choice == "0":
        test_window_activation()
    elif choice == "1":
        test_single_shot()
    elif choice == "2":
        test_multiple_shots(4)
    elif choice == "3":
        test_multiple_shots(8)
    else:
        print("❌ 잘못된 선택")