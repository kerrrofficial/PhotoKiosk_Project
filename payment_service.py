import requests
import json
import time  # 파일 상단에 추가
from datetime import datetime

class KSNETPayment:
    """KSNET 결제 처리 클래스 (HTTP API 방식)"""
    
    def __init__(self, host='localhost', port=27098):
        self.base_url = f"http://{host}:{port}"
    
    def approve(self, amount: int, installment: int = 0, timeout: int = 120) -> dict:
        """
        신용카드 승인
        
        Args:
            amount: 금액 (원)
            installment: 할부 개월 (0=일시불)
            timeout: 타임아웃 (초)
        """
        # KSCAT API 요청 형식 (일반적인 형식)
        params = {
            'trade_type': 'D1',  # 신용승인
            'amount': str(amount),
            'install': f'{installment:02d}',
            'timestamp': datetime.now().strftime('%Y%m%d%H%M%S')
        }
        
        print(f"[Payment] 승인 요청: {amount}원")
        print(f"[Payment] URL: {self.base_url}/card")
        print(f"[Payment] Params: {params}")
        
        try:
            # POST 방식 시도
            response = requests.post(
                f"{self.base_url}/card",
                data=params,
                timeout=timeout
            )
            
            print(f"[Payment] Response Status: {response.status_code}")

            # 1) 원문(bytes) 기반으로 최대한 복원
            raw_bytes = response.content or b""
            text_utf8 = raw_bytes.decode("utf-8", errors="ignore").strip()
            text_cp949 = raw_bytes.decode("cp949", errors="ignore").strip()
            result = text_cp949 if text_cp949 else text_utf8
            if not result:
                result = (response.text or "").strip()

            print(f"[Payment] Response Text (repr): {repr(result)}")

                        # 2) 여기서부터 "진짜 승인/취소가 확정될 때만 성공/실패"로 처리
            if response.status_code != 200:
                return {
                    "success": False,
                    "message": f"HTTP 에러: {response.status_code}",
                    "raw": result
                }

            fail_keywords = ["취소", "거절", "실패", "CANCEL", "FAIL", "DENY", "ERROR"]
            success_keywords = ["승인", "정상", "SUCCESS", "OK", "APPROVE"]

            # 실패 키워드면 즉시 실패
            if any(k in result for k in fail_keywords):
                return {"success": False, "message": "결제 실패/취소", "raw": result}

            # 성공 키워드면 즉시 성공
            if any(k in result for k in success_keywords):
                return {"success": True, "message": "결제 승인 완료", "raw": result}

            # 결과가 '()' 또는 빈 값이면: 아직 승인/취소가 확정되지 않은 상태로 보고 기다림
            print("[Payment] 승인 결과 대기중...")

            deadline = time.time() + timeout
            poll_interval = 0.5

            while time.time() < deadline:
                time.sleep(poll_interval)

                # ⚠️ 주의: 이 폴링이 "새 결제"를 다시 만드는 방식이면 위험할 수 있음(중복결제)
                # 지금은 KSCAT 응답이 '()'로 와서 결과 확인용으로 시도하는 디버깅용 방식
                r = requests.post(f"{self.base_url}/card", data=params, timeout=10)

                raw = r.content or b""
                t_utf8 = raw.decode("utf-8", errors="ignore").strip()
                t_cp949 = raw.decode("cp949", errors="ignore").strip()
                res = t_cp949 if t_cp949 else t_utf8
                if not res:
                    res = (r.text or "").strip()

                print(f"[Payment] Poll Status: {r.status_code}, Text: {repr(res)}")

                if r.status_code != 200:
                    continue

                if any(k in res for k in fail_keywords):
                    return {"success": False, "message": "결제 실패/취소", "raw": res}

                if any(k in res for k in success_keywords):
                    return {"success": True, "message": "결제 승인 완료", "raw": res}

            return {"success": False, "message": "결제 응답 타임아웃(승인 결과 미확정)", "raw": result}

        
        except requests.exceptions.ConnectionError:
            return {
                'success': False,
                'message': 'KSCAT 서비스가 실행되지 않았습니다.'
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'오류: {str(e)}'
            }
    
    def check_service(self) -> bool:
        """KSCAT 서비스 상태 확인"""
        try:
            # 단순 연결 테스트
            response = requests.get(
                f"{self.base_url}/",
                timeout=3
            )
            return True
        except:
            return False


# 테스트
if __name__ == "__main__":
    print("=== KSNET 결제 테스트 ===\n")
    
    payment = KSNETPayment()
    
    # 1. 서비스 확인
    print("[1] KSCAT 서비스 확인...")
    if payment.check_service():
        print("✅ 서비스 실행 중\n")
    else:
        print("❌ 서비스 미실행. KSCAT에서 '서비스 시작' 버튼을 누르세요.\n")
        exit(1)
    
    # 2. 100원 승인
    print("[2] 100원 결제 테스트...")
    print("리더기에 카드를 태그하거나 삽입하세요...\n")
    
    result = payment.approve(amount=100)
    
    print("\n=== 결과 ===")
    if result['success']:
        print("✅ 결제 성공!")
    else:
        print(f"❌ 결제 실패: {result['message']}")
    
    print(f"\n상세 응답:\n{result.get('raw', '')}")