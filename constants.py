# constants.py
LAYOUT_OPTIONS_MASTER = {
    "half": {
        "v2": "세로 2컷", "v3": "세로 3컷", "v4": "세로 4컷",
        "h2": "가로 2컷", "h3": "가로 3컷", "h4": "가로 4컷"
    },
    "full": {
        "v1": "세로 1컷", "v2": "세로 2컷", "v4a": "세로 4컷(A)", "v4b": "세로 4컷(B)", "v9": "세로 9컷",
        "h2": "가로 2컷", "h4": "가로 4컷", "h5": "가로 5컷", "h10": "가로 10컷"
    },
    "a4": {
        "4cut": "4컷"
    }
}

# 레이아웃별 실제 슬롯 수 (촬영/선택 컷수)
LAYOUT_SLOT_COUNT = {
    # 하프컷 - 좌우 각각 독립 배치
    "half_v2": 4,   # 좌2 + 우2
    "half_v3": 6,   # 좌3 + 우3
    "half_v4": 8,   # 좌4 + 우4
    "half_h2": 4,   # 상2 + 하2
    "half_h3": 6,   # 상3 + 하3
    "half_h4": 8,   # 상4 + 하4
    # 풀컷
    "full_v1": 1,
    "full_v2": 2,
    "full_v4a": 4,
    "full_v4b": 4,
    "full_v9": 9,
    "full_h2": 2,
    "full_h4": 4,
    "full_h5": 5,
    "full_h10": 10,
}

DEFAULT_SHOOT_COUNT = 8
MAX_SHOOT_COUNT = 12