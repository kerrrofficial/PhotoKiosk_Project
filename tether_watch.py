import time
from pathlib import Path

WATCH_DIR = Path("incoming_photos")
SUPPORTED_EXT = {".jpg", ".jpeg", ".png"}

def get_latest_file(folder: Path) -> Path | None:
    files = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in SUPPORTED_EXT]
    if not files:
        return None
    # 수정시간이 가장 최신인 파일
    return max(files, key=lambda f: f.stat().st_mtime)

def main():
    WATCH_DIR.mkdir(exist_ok=True)
    print(f"[watch] watching folder: {WATCH_DIR.resolve()}")

    last_seen: Path | None = None

    while True:
        latest = get_latest_file(WATCH_DIR)
        if latest and latest != last_seen:
            last_seen = latest
            print(f"[watch] NEW FILE: {latest.name} ({latest.stat().st_size} bytes)")
        time.sleep(0.5)

if __name__ == "__main__":
    main()
