"""Upload all files from datasets/ to the running /api/upload endpoint."""
import base64
import os
import sys
from pathlib import Path

import requests

API_URL = os.environ.get("API_URL", "http://localhost:8000")
USERNAME = os.environ.get("UPLOAD_USERNAME", "admin")
PASSWORD = os.environ.get("UPLOAD_PASSWORD", "adminpass123")
DATASETS_ROOT = Path(__file__).parent / "datasets"
SUPPORTED_EXTENSIONS = {".pdf", ".csv", ".xls", ".xlsx"}


def get_token() -> str:
    r = requests.post(f"{API_URL}/api/login", json={"username": USERNAME, "password": PASSWORD}, timeout=10)
    if r.status_code == 200:
        print(f"Logged in as '{USERNAME}'")
        return r.json()["token"]

    r = requests.post(f"{API_URL}/api/signup", json={"username": USERNAME, "password": PASSWORD}, timeout=10)
    if r.status_code == 201:
        print(f"Signed up and logged in as '{USERNAME}'")
        return r.json()["token"]

    print(f"Authentication failed: {r.status_code} {r.text}", file=sys.stderr)
    sys.exit(1)


def upload_file(file_path: Path, token: str) -> bool:
    content = base64.b64encode(file_path.read_bytes()).decode()
    payload = {
        "files": [{
            "filename": file_path.name,
            "content": content,
            "size": file_path.stat().st_size,
        }]
    }
    r = requests.post(
        f"{API_URL}/api/upload",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=300,
    )
    if r.status_code == 200:
        print(f"  OK  {r.json()}")
        return True
    print(f"  ERR {r.status_code}: {r.json()}", file=sys.stderr)
    return False


def main() -> None:
    files = sorted(
        f for f in DATASETS_ROOT.rglob("*")
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    if not files:
        print("No supported files found in datasets/")
        return

    print(f"Found {len(files)} file(s) to upload\n")
    token = get_token()

    success, failed = 0, 0
    for f in files:
        rel = f.relative_to(DATASETS_ROOT.parent)
        print(f"Uploading {rel} ...")
        if upload_file(f, token):
            success += 1
        else:
            failed += 1

    print(f"\nDone: {success} succeeded, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
