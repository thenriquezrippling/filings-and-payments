"""
sync_to_drive.py — Syncs changed taxops/*.py files to the TaxOps Automation Suite
Google Drive folder on every push to main.

Called by .github/workflows/sync-to-drive.yml with changed file paths as arguments.
Requires GOOGLE_SERVICE_ACCOUNT_JSON environment variable (GitHub secret).

Drive folder: https://drive.google.com/drive/folders/1Kou1Xk_DH12rthf9Tkprk01KzatMtyYs
"""
import os
import sys
import json

from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
from google.oauth2 import service_account

DRIVE_FOLDER_ID = "1Kou1Xk_DH12rthf9Tkprk01KzatMtyYs"
SCOPES          = ["https://www.googleapis.com/auth/drive"]


def get_service():
    creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not creds_json:
        print("FATAL: GOOGLE_SERVICE_ACCOUNT_JSON not set", file=sys.stderr)
        sys.exit(1)
    creds = service_account.Credentials.from_service_account_info(
        json.loads(creds_json), scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def find_file(service, filename):
    """Return the Drive file ID if the file already exists in the folder."""
    q = f"name='{filename}' and '{DRIVE_FOLDER_ID}' in parents and trashed=false"
    res = service.files().list(q=q, fields="files(id,name)").execute()
    files = res.get("files", [])
    return files[0]["id"] if files else None


def sync_file(service, filepath):
    filename = os.path.basename(filepath)
    with open(filepath, "rb") as f:
        content = f.read()

    media   = MediaInMemoryUpload(content, mimetype="text/plain", resumable=False)
    file_id = find_file(service, filename)

    if file_id:
        service.files().update(fileId=file_id, media_body=media).execute()
        print(f"  Updated : {filename}")
    else:
        metadata = {"name": filename, "parents": [DRIVE_FOLDER_ID]}
        service.files().create(body=metadata, media_body=media,
                               fields="id").execute()
        print(f"  Created : {filename}")


if __name__ == "__main__":
    files = [f for f in sys.argv[1:] if f.endswith(".py")]
    if not files:
        print("[sync] No Python files to sync — nothing to do.")
        sys.exit(0)

    print(f"[sync] Syncing {len(files)} file(s) to Google Drive...")
    svc = get_service()
    errors = []
    for filepath in files:
        if not os.path.exists(filepath):
            print(f"  Skipped : {os.path.basename(filepath)} (deleted from repo)")
            continue
        try:
            sync_file(svc, filepath)
        except Exception as e:
            print(f"  ERROR   : {os.path.basename(filepath)} — {e}", file=sys.stderr)
            errors.append(filepath)

    if errors:
        print(f"[sync] Completed with {len(errors)} error(s).", file=sys.stderr)
        sys.exit(1)
    else:
        print("[sync] All files synced successfully.")
