"""(Tùy chọn) Lấy GOOGLE_REFRESH_TOKEN bằng script thay vì OAuth Playground.
Chạy trên máy:  pip install google-auth-oauthlib  &&  python scripts/get_google_token.py
"""
from google_auth_oauthlib.flow import InstalledAppFlow

cid = input("GOOGLE_CLIENT_ID: ").strip()
secret = input("GOOGLE_CLIENT_SECRET: ").strip()
flow = InstalledAppFlow.from_client_config(
    {"installed": {"client_id": cid, "client_secret": secret,
                   "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                   "token_uri": "https://oauth2.googleapis.com/token",
                   "redirect_uris": ["http://localhost"]}},
    scopes=["https://www.googleapis.com/auth/drive"])
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
print("\nGOOGLE_REFRESH_TOKEN =", creds.refresh_token)
