import os
import time
import json
import logging
import requests
import msal
from tqdm import tqdm

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('onedrive_uploader')

class OneDriveUploader:
    def __init__(self, client_id, client_secret, tenant_id='common', redirect_uri='http://localhost:8000/callback',
                 scopes=None, token_path='./onedrive_token.json', upload_folder='/BTDownloads'):
        """
        初始化 OneDrive 上傳器
        
        Args:
            client_id (str): Microsoft 應用程式 ID
            client_secret (str): Microsoft 應用程式密鑰
            tenant_id (str): Microsoft 租戶 ID (通常為 'common')
            redirect_uri (str): 應用程式重定向 URI
            scopes (list): 授權範圍
            token_path (str): 保存 token 的檔案路徑
            upload_folder (str): OneDrive 上傳目標資料夾路徑
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id
        self.redirect_uri = redirect_uri
        self.scopes = scopes or ['Files.ReadWrite', 'Files.ReadWrite.All', 'offline_access']
        self.token_path = token_path
        self.upload_folder = upload_folder
        self.token = None
        self.app = None
        
        self._init_app()
        self._load_token()
    
    def _init_app(self):
        """初始化 MSAL 應用程式"""
        self.app = msal.ConfidentialClientApplication(
            self.client_id,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            client_credential=self.client_secret
        )
        logger.info("Microsoft MSAL app initialized")
    
    def _load_token(self):
        """從檔案加載 token"""
        try:
            if os.path.exists(self.token_path):
                with open(self.token_path, 'r') as f:
                    self.token = json.load(f)
                logger.info("Token loaded from file")
        except Exception as e:
            logger.error(f"Error loading token: {str(e)}")
            self.token = None
    
    def _save_token(self):
        """保存 token 到檔案"""
        try:
            with open(self.token_path, 'w') as f:
                json.dump(self.token, f)
            logger.info("Token saved to file")
        except Exception as e:
            logger.error(f"Error saving token: {str(e)}")
    
    def _acquire_token_silently(self):
        """嘗試靜默獲取 token"""
        if not self.token:
            return None
        
        accounts = self.app.get_accounts()
        if accounts:
            result = self.app.acquire_token_silent(self.scopes, account=accounts[0])
            if result:
                self.token = result
                self._save_token()
                return result
        return None
    
    def authenticate_device_flow(self):
        """
        使用設備流程進行身份驗證，適合無頭環境（如服務器）
        
        Returns:
            bool: 身份驗證是否成功
        """
        flow = self.app.initiate_device_flow(scopes=self.scopes)
        
        if "user_code" not in flow:
            logger.error(f"Failed to create device flow: {json.dumps(flow, indent=4)}")
            return False
        
        print(f"\n{flow['message']}\n")
        
        result = self.app.acquire_token_by_device_flow(flow)
        
        if "access_token" in result:
            self.token = result
            self._save_token()
            logger.info("Authentication successful")
            return True
        else:
            logger.error(f"Authentication failed: {json.dumps(result, indent=4)}")
            return False
    
    def authenticate(self):
        """
        進行身份驗證，如果靜默方式失敗則使用設備流程
        
        Returns:
            bool: 身份驗證是否成功
        """
        result = self._acquire_token_silently()
        if result:
            logger.info("Authentication successful (silent)")
            return True
        
        return self.authenticate_device_flow()
    
    def is_authenticated(self):
        """
        檢查是否已經通過身份驗證
        
        Returns:
            bool: 是否已認證
        """
        if not self.token or "access_token" not in self.token:
            return False
        
        # 檢查 token 是否過期
        expires_at = self.token.get("expires_at", 0)
        if expires_at < time.time():
            # 嘗試刷新 token
            result = self._acquire_token_silently()
            if not result:
                return False
        
        return True
    
    def create_folder(self, folder_path):
        """
        在 OneDrive 中建立資料夾
        
        Args:
            folder_path (str): 資料夾路徑（例如 '/documents/photos'）
            
        Returns:
            dict: 建立的資料夾信息
        """
        if not self.is_authenticated():
            if not self.authenticate():
                return {"error": "Authentication failed"}
        
        # 移除開頭的斜線
        if folder_path.startswith('/'):
            folder_path = folder_path[1:]
        
        # 按層次建立資料夾
        parts = folder_path.split('/')
        current_path = ''
        parent_id = None
        
        for part in parts:
            if not part:
                continue
            
            current_path += '/' + part
            
            # 檢查資料夾是否存在
            existing = self.get_item_by_path(current_path)
            if existing and 'error' not in existing:
                parent_id = existing['id']
                continue
            
            # 建立新資料夾
            url = "https://graph.microsoft.com/v1.0/me/drive/items"
            if parent_id:
                url = f"https://graph.microsoft.com/v1.0/me/drive/items/{parent_id}/children"
            
            headers = {
                'Authorization': f"Bearer {self.token['access_token']}",
                'Content-Type': 'application/json'
            }
            
            data = {
                "name": part,
                "folder": {},
                "@microsoft.graph.conflictBehavior": "rename"
            }
            
            response = requests.post(url, headers=headers, json=data)
            
            if response.status_code == 201:
                folder_info = response.json()
                parent_id = folder_info['id']
                logger.info(f"Created folder: {current_path}")
            else:
                error_message = f"Failed to create folder {current_path}: {response.status_code} - {response.text}"
                logger.error(error_message)
                return {"error": error_message}
        
        return self.get_item_by_path(folder_path)
    
    def get_item_by_path(self, path):
        """
        通過路徑獲取 OneDrive 中的項目
        
        Args:
            path (str): 項目路徑
            
        Returns:
            dict: 項目信息
        """
        if not self.is_authenticated():
            if not self.authenticate():
                return {"error": "Authentication failed"}
        
        # 移除開頭的斜線
        if path.startswith('/'):
            path = path[1:]
        
        # 空路徑表示根目錄
        if not path:
            url = "https://graph.microsoft.com/v1.0/me/drive/root"
        else:
            url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{path}"
        
        headers = {
            'Authorization': f"Bearer {self.token['access_token']}"
        }
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            return response.json()
        else:
            error_message = f"Failed to get item at path {path}: {response.status_code} - {response.text}"
            logger.error(error_message)
            return {"error": error_message}
    
    def upload_file(self, file_path, destination_folder=None, show_progress=True):
        """
        上傳檔案到 OneDrive
        
        Args:
            file_path (str): 要上傳的檔案本地路徑
            destination_folder (str): OneDrive 目標資料夾 (默認為 self.upload_folder)
            show_progress (bool): 是否顯示進度條
            
        Returns:
            dict: 上傳結果
        """
        if not self.is_authenticated():
            if not self.authenticate():
                return {"error": "Authentication failed"}
        
        destination_folder = destination_folder or self.upload_folder
        
        # 確保目標資料夾存在
        folder_info = self.create_folder(destination_folder)
        if 'error' in folder_info:
            return folder_info
        
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        
        logger.info(f"Uploading file: {file_name} ({file_size/1024/1024:.2f} MB)")
        
        if file_size <= 4 * 1024 * 1024:  # 小於 4MB 的檔案使用簡單上傳
            return self._simple_upload(file_path, destination_folder)
        else:
            # 大檔案使用分段上傳
            return self._chunked_upload(file_path, destination_folder, show_progress)
    
    def _simple_upload(self, file_path, destination_folder):
        """
        簡單上傳（適用於小檔案）
        
        Args:
            file_path (str): 要上傳的檔案本地路徑
            destination_folder (str): OneDrive 目標資料夾
            
        Returns:
            dict: 上傳結果
        """
        file_name = os.path.basename(file_path)
        
        # 移除開頭的斜線
        if destination_folder.startswith('/'):
            destination_folder = destination_folder[1:]
        
        url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{destination_folder}/{file_name}:/content"
        
        headers = {
            'Authorization': f"Bearer {self.token['access_token']}"
        }
        
        with open(file_path, 'rb') as f:
            response = requests.put(url, headers=headers, data=f)
        
        if response.status_code in (200, 201):
            logger.info(f"Successfully uploaded file: {file_name}")
            return response.json()
        else:
            error_message = f"Failed to upload file {file_name}: {response.status_code} - {response.text}"
            logger.error(error_message)
            return {"error": error_message}
    
    def _chunked_upload(self, file_path, destination_folder, show_progress=True):
        """
        分段上傳（適用於大檔案）
        
        Args:
            file_path (str): 要上傳的檔案本地路徑
            destination_folder (str): OneDrive 目標資料夾
            show_progress (bool): 是否顯示進度條
            
        Returns:
            dict: 上傳結果
        """
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        
        # 建立上傳會話
        url = "https://graph.microsoft.com/v1.0/me/drive/root:/" + destination_folder.strip('/') + "/" + file_name + ":/createUploadSession"
        
        headers = {
            'Authorization': f"Bearer {self.token['access_token']}",
            'Content-Type': 'application/json'
        }
        
        data = {
            "item": {
                "@microsoft.graph.conflictBehavior": "rename"
            }
        }
        
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code != 200:
            error_message = f"Failed to create upload session: {response.status_code} - {response.text}"
            logger.error(error_message)
            return {"error": error_message}
        
        upload_url = response.json()['uploadUrl']
        
        # 分段上傳
        chunk_size = 10 * 1024 * 1024  # 10 MB 塊
        total_chunks = (file_size + chunk_size - 1) // chunk_size
        
        pbar = None
        if show_progress:
            pbar = tqdm(total=file_size, unit='B', unit_scale=True, desc=f"Uploading {file_name}")
        
        with open(file_path, 'rb') as f:
            for chunk_num in range(total_chunks):
                start = chunk_num * chunk_size
                end = min(file_size, start + chunk_size) - 1
                
                # 讀取當前塊
                f.seek(start)
                chunk_data = f.read(chunk_size)
                
                # 上傳當前塊
                headers = {
                    'Content-Length': str(end - start + 1),
                    'Content-Range': f'bytes {start}-{end}/{file_size}'
                }
                
                response = requests.put(upload_url, headers=headers, data=chunk_data)
                
                if show_progress:
                    pbar.update(len(chunk_data))
                
                # 檢查是否完成
                if response.status_code in (200, 201, 202):
                    if response.status_code in (200, 201):
                        if show_progress:
                            pbar.close()
                        logger.info(f"Successfully uploaded file: {file_name}")
                        return response.json()
                else:
                    if show_progress:
                        pbar.close()
                    error_message = f"Failed chunk upload for file {file_name}: {response.status_code} - {response.text}"
                    logger.error(error_message)
                    return {"error": error_message}
        
        # 如果沒有收到完成響應但所有塊已上傳
        if show_progress:
            pbar.close()
        return {"error": "Upload completed but no confirmation received"}
    
    def upload_folder(self, folder_path, destination_folder=None):
        """
        上傳整個資料夾到 OneDrive
        
        Args:
            folder_path (str): 要上傳的資料夾本地路徑
            destination_folder (str): OneDrive 目標資料夾 (默認為 self.upload_folder)
            
        Returns:
            dict: 上傳結果匯總
        """
        if not os.path.isdir(folder_path):
            return {"error": f"Not a directory: {folder_path}"}
        
        destination_folder = destination_folder or self.upload_folder
        folder_name = os.path.basename(folder_path)
        target_folder = f"{destination_folder}/{folder_name}".replace('//', '/')
        
        # 建立目標資料夾
        folder_info = self.create_folder(target_folder)
        if 'error' in folder_info:
            return folder_info
        
        results = {
            "success": [],
            "error": []
        }
        
        # 遍歷資料夾
        for root, dirs, files in os.walk(folder_path):
            # 計算相對路徑
            relative_path = os.path.relpath(root, folder_path)
            if relative_path == ".":
                relative_path = ""
            
            # 構建目標路徑
            current_target = f"{target_folder}/{relative_path}".replace('//', '/')
            
            # 上傳檔案
            for file in files:
                file_path = os.path.join(root, file)
                result = self.upload_file(file_path, current_target)
                
                if 'error' in result:
                    results["error"].append({
                        "file": file_path,
                        "error": result["error"]
                    })
                else:
                    results["success"].append({
                        "file": file_path,
                        "result": result
                    })
        
        return results 