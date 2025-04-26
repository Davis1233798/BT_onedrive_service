import os
from dotenv import load_dotenv

# 加載環境變數
load_dotenv()

# BT 下載設定
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', './downloads')
MAX_DOWNLOAD_RATE = int(os.getenv('MAX_DOWNLOAD_RATE', '0'))  # KB/s, 0表示無限制
MAX_UPLOAD_RATE = int(os.getenv('MAX_UPLOAD_RATE', '50'))  # KB/s

# OneDrive API設定
CLIENT_ID = os.getenv('ONEDRIVE_CLIENT_ID')
CLIENT_SECRET = os.getenv('ONEDRIVE_CLIENT_SECRET')
TENANT_ID = os.getenv('ONEDRIVE_TENANT_ID', 'common')
REDIRECT_URI = os.getenv('ONEDRIVE_REDIRECT_URI', 'http://localhost:8000/callback')
SCOPES = ['Files.ReadWrite', 'Files.ReadWrite.All', 'offline_access']
ONEDRIVE_UPLOAD_FOLDER = os.getenv('ONEDRIVE_UPLOAD_FOLDER', '/BTDownloads')

# 服務設定
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '300'))  # 檢查種子狀態的間隔（秒） 