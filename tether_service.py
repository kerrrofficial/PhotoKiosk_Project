import time
from pathlib import Path
from datetime import datetime

print("[tether_service] LOADED from:", __file__)
BASE_DIR = Path(__file__).resolve().parent  # tether_service.py가 있는 폴더(=프로젝트 루트)
WATCH_DIR = BASE_DIR / "incoming_photos"
SESSIONS_DIR = BASE_DIR / "sessions"

SUPPORTED_EXT = {".jpg", ".jpeg", ".png"}

def _list_media_files(folder: Path):
    return sorted(
        [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in SUPPORTED_EXT],
        key=lambda x: x.name.lower()
    )

def _wait_for_new_files_by_name(window_sec: int):
    before = {f.name for f in _list_media_files(WATCH_DIR)}
    end_time = time.time() + window_sec
    collected = []
    seen = set()

    while time.time() < end_time:
        for f in _list_media_files(WATCH_DIR):
            if f.name in before or f.name in seen:
                continue
            try:
                size1 = f.stat().st_size
            except FileNotFoundError:
                continue
            if size1 <= 0:
                continue

            time.sleep(0.3)
            try:
                size2 = f.stat().st_size
            except FileNotFoundError:
                continue

            if size2 == size1 and size2 > 0:
                collected.append(f)
                seen.add(f.name)

        time.sleep(0.2)

    return collected

def _pick_best_one(files):
    if not files:
        return None
    return max(files, key=lambda f: f.stat().st_size)

def capture_one_photo_blocking(capture_window_sec: int = 15) -> Path | None:
    """
    '지금부터 capture_window_sec 동안 들어온 새 파일'을 감지해서
    가장 큰 파일 1장을 반환.
    (나중에 EOS Utility가 실제 촬영 파일을 저장하면 그대로 동작)
    """
    print("[tether_service] capture_one_photo_blocking START, window=", capture_window_sec)
    print("[tether_service] WATCH_DIR =", WATCH_DIR)
    print("[tether_service] SESSIONS_DIR =", SESSIONS_DIR)


    WATCH_DIR.mkdir(exist_ok=True)
    SESSIONS_DIR.mkdir(exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_path = SESSIONS_DIR / f"session_{ts}"
    session_path.mkdir(parents=True, exist_ok=True)

    new_files = _wait_for_new_files_by_name(capture_window_sec)
    best = _pick_best_one(new_files)
    if not best:
        return None

    # 세션 폴더로 복사해두고, 그 경로를 반환 (프로그램이 안정적으로 접근 가능)
    dest = session_path / best.name
    dest.write_bytes(best.read_bytes())
    (session_path / "latest.txt").write_text(str(dest.resolve()), encoding="utf-8")
    return dest

import shutil

def capture_many_photos_blocking(expected_count: int = 12, timeout_sec: int = 60) -> list[Path]:
    """
    timeout_sec 동안 WATCH_DIR에 새로 생기는 파일을 감지해서 expected_count개 모으면 반환.
    각 파일은 sessions/session_xxx 폴더로 복사해서 안정적인 경로로 만들어둔다.
    """
    WATCH_DIR.mkdir(exist_ok=True)
    SESSIONS_DIR.mkdir(exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_path = SESSIONS_DIR / f"session_{ts}"
    session_path.mkdir(parents=True, exist_ok=True)

    # 세션 시작 시점의 파일 목록 스냅샷
    before = {f.name for f in _list_media_files(WATCH_DIR)}
    collected: list[Path] = []
    seen = set()

    end_time = time.time() + timeout_sec

    while time.time() < end_time and len(collected) < expected_count:
        for f in _list_media_files(WATCH_DIR):
            if f.name in before or f.name in seen:
                continue

            # 파일 쓰기 완료(사이즈 안정) 확인
            try:
                size1 = f.stat().st_size
            except FileNotFoundError:
                continue
            if size1 <= 0:
                continue

            time.sleep(0.3)
            try:
                size2 = f.stat().st_size
            except FileNotFoundError:
                continue

            if size2 == size1 and size2 > 0:
                seen.add(f.name)

                # 세션 폴더로 복사 (번호 붙여서 저장)
                dest = session_path / f"{len(collected)+1:02d}_{f.name}"
                shutil.copy2(f, dest)
                collected.append(dest)

                # 디버그용(원하면 나중에 제거)
                print(f"[tether_service] +{len(collected)}/{expected_count} -> {dest.name}")

                if len(collected) >= expected_count:
                    break

        time.sleep(0.1)

    # 마지막으로 latest.txt 기록(가장 마지막 파일)
    if collected:
        (session_path / "latest.txt").write_text(str(collected[-1].resolve()), encoding="utf-8")

    return collected
