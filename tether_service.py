import time
import shutil
from pathlib import Path
from datetime import datetime

print("[tether_service] LOADED from:", __file__)
BASE_DIR = Path(__file__).resolve().parent
WATCH_DIR = BASE_DIR / "incoming_photos"
SESSIONS_DIR = BASE_DIR / "sessions"

SUPPORTED_EXT = {".jpg", ".jpeg", ".png"}

def _list_media_files(folder: Path):
    return sorted(
        [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in SUPPORTED_EXT],
        key=lambda x: x.name.lower()
    )

def _wait_for_new_files_by_name(window_sec: int, pre_snapshot: set = None):
    before = pre_snapshot if pre_snapshot is not None else {f.name for f in _list_media_files(WATCH_DIR)}
    print(f"[tether_service] 감시 시작 - 기존 파일 {len(before)}개: {sorted(before)[-3:] if before else '없음'}")
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
                print(f"[tether_service] 새 파일 감지: {f.name}")
                return collected  # 1장 감지 즉시 반환

        time.sleep(0.2)

    return collected

def _pick_best_one(files):
    if not files:
        return None
    return max(files, key=lambda f: f.stat().st_size)

def capture_one_photo_blocking(capture_window_sec: int = 15, pre_snapshot: set = None) -> Path | None:
    """
    pre_snapshot 기준으로 새로 생긴 파일 1장을 감지해서 반환.
    """
    print("[tether_service] capture_one_photo_blocking START, window=", capture_window_sec)
    print("[tether_service] WATCH_DIR =", WATCH_DIR)
    print("[tether_service] SESSIONS_DIR =", SESSIONS_DIR)

    WATCH_DIR.mkdir(exist_ok=True)
    SESSIONS_DIR.mkdir(exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_path = SESSIONS_DIR / f"session_{ts}"
    session_path.mkdir(parents=True, exist_ok=True)

    new_files = _wait_for_new_files_by_name(capture_window_sec, pre_snapshot=pre_snapshot)
    best = _pick_best_one(new_files)
    if not best:
        print("[tether_service] ⚠️ 새 파일 없음 - 타임아웃")
        return None

    dest = session_path / best.name
    dest.write_bytes(best.read_bytes())
    (session_path / "latest.txt").write_text(str(dest.resolve()), encoding="utf-8")
    print(f"[tether_service] 저장 완료: {dest}")
    return dest

def capture_many_photos_blocking(expected_count: int = 12, timeout_sec: int = 60) -> list[Path]:
    """
    timeout_sec 동안 WATCH_DIR에 새로 생기는 파일을 감지해서 expected_count개 모으면 반환.
    """
    WATCH_DIR.mkdir(exist_ok=True)
    SESSIONS_DIR.mkdir(exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_path = SESSIONS_DIR / f"session_{ts}"
    session_path.mkdir(parents=True, exist_ok=True)

    before = {f.name for f in _list_media_files(WATCH_DIR)}
    collected: list[Path] = []
    seen = set()

    end_time = time.time() + timeout_sec

    while time.time() < end_time and len(collected) < expected_count:
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
                seen.add(f.name)
                dest = session_path / f"{len(collected)+1:02d}_{f.name}"
                shutil.copy2(f, dest)
                collected.append(dest)
                print(f"[tether_service] +{len(collected)}/{expected_count} -> {dest.name}")

                if len(collected) >= expected_count:
                    break

        time.sleep(0.1)

    if collected:
        (session_path / "latest.txt").write_text(str(collected[-1].resolve()), encoding="utf-8")

    return collected
