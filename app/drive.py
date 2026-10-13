"""Google Drive: list new videos, download, upload results, move processed files."""
import io
import re

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from . import config

_svc = None


def svc():
    global _svc
    if _svc is None:
        creds = Credentials(None, refresh_token=config.GOOGLE_REFRESH_TOKEN,
                            token_uri="https://oauth2.googleapis.com/token",
                            client_id=config.GOOGLE_CLIENT_ID, client_secret=config.GOOGLE_CLIENT_SECRET,
                            scopes=["https://www.googleapis.com/auth/drive"])
        _svc = build("drive", "v3", credentials=creds, cache_discovery=False)
    return _svc


def list_inbox():
    q = f"'{config.DRIVE_INBOX_FOLDER_ID}' in parents and mimeType contains 'video/' and trashed=false"
    res = svc().files().list(q=q, fields="files(id,name,size,description)", orderBy="createdTime",
                             pageSize=50).execute()
    return res.get("files", [])


def download(file_id, path):
    req = svc().files().get_media(fileId=file_id)
    with io.FileIO(path, "wb") as fh:
        dl = MediaIoBaseDownload(fh, req, chunksize=16 * 1024 * 1024)
        done = False
        while not done:
            _, done = dl.next_chunk()
    return path


def upload(path, name, folder_id, description=""):
    media = MediaFileUpload(path, mimetype="video/mp4", resumable=True)
    f = svc().files().create(body={"name": name, "parents": [folder_id], "description": description},
                             media_body=media, fields="id,webViewLink").execute()
    return f["id"], f.get("webViewLink")


def move(file_id, to_folder):
    f = svc().files().get(fileId=file_id, fields="parents").execute()
    svc().files().update(fileId=file_id, addParents=to_folder,
                         removeParents=",".join(f.get("parents", [])), fields="id").execute()


def product_link_from(name, description=""):
    """Find the Shopee link: in the file description, or in the file name after '__'.
    e.g.  'pancake__60SJhy1h9E.mp4'  ->  https://s.shopee.vn/60SJhy1h9E"""
    m = re.search(r"https?://\S*shopee\S+", description or "")
    if m:
        return m.group(0)
    stem = re.sub(r"\.[A-Za-z0-9]+$", "", name)
    if "__" in stem:
        code = stem.split("__")[-1].strip()
        if code.startswith("http"):
            return code
        if re.fullmatch(r"[A-Za-z0-9]{6,20}", code):
            return config.SHOPEE_SHORT_DOMAIN + code
    return None
