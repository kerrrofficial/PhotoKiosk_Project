import time
import shutil
from pathlib import Path
from datetime import datetime

def pick_best_one(files):
    """후보들 중 '가장 용량이 큰 파일' 1개만 선택"""
    if not files:
        return None
    return max(files, key=lambda f: f.stat().st_size)

def write_latest_path_file(session_path: Path, best_file: Path):
    """
    main.py 같은 다른 코드가 쉽게 읽을 수 있도록
    '마지막 촬영 파일 경로'를 텍스트로 저장
    """
    out = session_path / "latest.txt"
    out.write_text(str(best_file.resolve()), encoding="utf-8")


WATCH_DIR = Path("incoming_photos")
SESSIONS_DIR = Path("sessions")
SUPPORTED_EXT = {".jpg", ".jpeg", ".png"}

CAPTURE_WINDOW_SEC = 15  # 세션 시작 후 기다릴 시간(초)

def list_media_files(folder: Path):
    return sorted([
        f for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXT
    ], key=lambda x: x.name.lower())

def make_session_folder() -> Path:
    SESSIONS_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_path = SESSIONS_DIR / f"session_{ts}"
    session_path.mkdir(parents=True, exist_ok=True)
    return session_path

def wait_for_new_files_by_name(window_sec: int):
    """
    세션 시작 직전의 파일 목록을 스냅샷으로 저장해두고,
    window_sec 동안 '새로 나타난 파일 이름'만 감지한다.
    """
    before = {f.name for f in list_media_files(WATCH_DIR)}
    collected = []
    seen = set()
    end_time = time.time() + window_sec

    while time.time() < end_time:
        now_files = list_media_files(WATCH_DIR)
        for f in now_files:
            if f.name in before:
                continue
            if f.name in seen:
                continue

            # 파일이 저장 중일 수 있으니, size가 안정적인지 확인
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
                print(f"[session] detected: {f.name} ({size2} bytes)")

        time.sleep(0.2)

    # 파일명 기준 정렬
    collected.sort(key=lambda x: x.name.lower())
    return collected

def copy_files_to_session(files, session_path: Path):
    moved = []
    for f in files:
        dest = session_path / f.name
        if dest.exists():
            dest = session_path / f"{f.stem}_{int(time.time())}{f.suffix}"
        shutil.copy2(f, dest)
        moved.append(dest)
    return moved

def main():
    WATCH_DIR.mkdir(exist_ok=True)
    print(f"[session] watch: {WATCH_DIR.resolve()}")
    print("[session] Press ENTER to start a capture session (simulate shutter).")

    while True:
        input()
        session_path = make_session_folder()
        print(f"[session] START -> {session_path.name} (window={CAPTURE_WINDOW_SEC}s)")

        files = wait_for_new_files_by_name(CAPTURE_WINDOW_SEC)

        if not files:
            print("[session] No new files captured.")
            continue

        moved = copy_files_to_session(files, session_path)

        best = pick_best_one(moved)
        if best:
            write_latest_path_file(session_path, best)
            print(f"[session] BEST = {best.name}")

        print(f"[session] DONE. moved {len(moved)} file(s) to {session_path}")


if __name__ == "__main__":
    main()
