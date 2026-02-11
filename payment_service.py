import requests
import json
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
            print(f"[Payment] Response Body: {response.text}")
            
            if response.status_code == 200:
                # 응답 파싱 (형식에 따라 다름)
                result = response.text
                
                # 성공 여부 확인 (실제 응답 형식 확인 필요)
                if '승인' in result or '정상' in result or 'SUCCESS' in result:
                    return {
                        'success': True,
                        'message': '결제 승인 완료',
                        'raw': result
                    }
                else:
                    return {
                        'success': False,
                        'message': '결제 실패',
                        'raw': result
                    }
            else:
                return {
                    'success': False,
                    'message': f'HTTP 에러: {response.status_code}'
                }
        
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