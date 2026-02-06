from PyQt6.QtPrintSupport import QPrinterInfo
from PyQt6.QtWidgets import QApplication
import sys

app = QApplication(sys.argv)

available_printers = QPrinterInfo.availablePrinters()

print("\n=== 🖨️ 설치된 프린터 목록 (이 이름을 복사해서 쓰세요) ===")
for p in available_printers:
    print(f"[{p.printerName()}]") # 이 안에 있는 이름이 진짜입니다.
print("====================================================\n")