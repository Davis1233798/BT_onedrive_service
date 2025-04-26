#!/usr/bin/env python3
import os
import time
import logging
import argparse
import schedule
import json
from pathlib import Path
from transmission_rpc import Client
from tqdm import tqdm

from scripts.bt_downloader_transmission import BTDownloader
from scripts.onedrive_uploader import OneDriveUploader
from config.config import (
    DOWNLOAD_DIR, MAX_DOWNLOAD_RATE, MAX_UPLOAD_RATE,
    CLIENT_ID, CLIENT_SECRET, TENANT_ID, REDIRECT_URI, SCOPES,
    ONEDRIVE_UPLOAD_FOLDER, CHECK_INTERVAL
)

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('bt_onedrive_service')

class BTOneDriveService:
    def __init__(self):
        """初始化 BT 下載和 OneDrive 上傳服務"""
        # 確保下載目錄存在
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        
        # 初始化 BT 下載器
        self.downloader = BTDownloader(
            download_dir=DOWNLOAD_DIR,
            max_download_rate=MAX_DOWNLOAD_RATE,
            max_upload_rate=MAX_UPLOAD_RATE
        )
        
        # 初始化 OneDrive 上傳器
        self.uploader = OneDriveUploader(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            tenant_id=TENANT_ID,
            redirect_uri=REDIRECT_URI,
            scopes=SCOPES,
            upload_folder=ONEDRIVE_UPLOAD_FOLDER
        )
        
        # 任務列表
        self.tasks_file = os.path.join(os.path.dirname(__file__), 'tasks.json')
        self.tasks = self._load_tasks()
        
        logger.info("BT OneDrive Service initialized")
    
    def _load_tasks(self):
        """從檔案中載入任務"""
        if os.path.exists(self.tasks_file):
            try:
                with open(self.tasks_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading tasks: {str(e)}")
        
        # 若文件不存在或讀取失敗，返回空任務列表
        return {
            "pending": [],
            "downloading": {},
            "completed": [],
            "failed": []
        }
    
    def _save_tasks(self):
        """保存任務到檔案"""
        try:
            with open(self.tasks_file, 'w') as f:
                json.dump(self.tasks, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving tasks: {str(e)}")
    
    def add_task(self, torrent_path_or_magnet):
        """
        添加下載任務
        
        Args:
            torrent_path_or_magnet (str): 種子檔案路徑或磁力連結
        
        Returns:
            bool: 是否成功添加任務
        """
        # 檢查任務是否已存在
        for task_type in ['pending', 'downloading', 'completed', 'failed']:
            task_list = self.tasks.get(task_type, [])
            if isinstance(task_list, list):
                if any(t.get('source') == torrent_path_or_magnet for t in task_list):
                    logger.warning(f"Task already exists: {torrent_path_or_magnet}")
                    return False
            elif isinstance(task_list, dict):
                if any(task_list[k].get('source') == torrent_path_or_magnet for k in task_list):
                    logger.warning(f"Task already exists: {torrent_path_or_magnet}")
                    return False
        
        # 添加到等待隊列
        self.tasks['pending'].append({
            'source': torrent_path_or_magnet,
            'added_time': time.time()
        })
        
        self._save_tasks()
        logger.info(f"Task added: {torrent_path_or_magnet}")
        return True
    
    def process_pending_tasks(self):
        """處理等待中的任務"""
        if not self.tasks['pending']:
            return
        
        for task in list(self.tasks['pending']):
            # 添加到下載器
            try:
                info_hash = self.downloader.add_torrent(task['source'])
                
                # 移動到下載中狀態
                self.tasks['downloading'][info_hash] = {
                    'source': task['source'],
                    'start_time': time.time(),
                    'added_time': task.get('added_time', time.time())
                }
                
                self.tasks['pending'].remove(task)
                self._save_tasks()
                
                logger.info(f"Started downloading: {task['source']}")
            except Exception as e:
                logger.error(f"Failed to start download: {task['source']} - {str(e)}")
                
                # 移動到失敗狀態
                task['error'] = str(e)
                self.tasks['failed'].append(task)
                self.tasks['pending'].remove(task)
                self._save_tasks()
    
    def check_downloads(self):
        """檢查下載中的任務狀態"""
        if not self.tasks['downloading']:
            return
        
        for info_hash, task in list(self.tasks['downloading'].items()):
            try:
                status = self.downloader.get_torrent_status(info_hash)
                
                # 更新任務狀態
                task['status'] = status
                self._save_tasks()
                
                # 檢查是否完成
                if status.get('is_finished', False):
                    logger.info(f"Download completed: {status.get('name', info_hash)}")
                    
                    # 獲取下載路徑
                    download_path = self.downloader.get_download_path(info_hash)
                    
                    if download_path:
                        # 上傳到 OneDrive
                        logger.info(f"Uploading to OneDrive: {download_path}")
                        
                        if os.path.isdir(download_path):
                            upload_result = self.uploader.upload_folder(download_path)
                        else:
                            upload_result = self.uploader.upload_file(download_path)
                        
                        task['upload_result'] = upload_result
                        
                        if 'error' not in upload_result:
                            logger.info(f"Upload successful: {download_path}")
                        else:
                            logger.error(f"Upload failed: {download_path} - {upload_result['error']}")
                    
                    # 移動到已完成狀態
                    task['complete_time'] = time.time()
                    self.tasks['completed'].append(task)
                    del self.tasks['downloading'][info_hash]
                    
                    # 可選：移除種子和文件
                    # self.downloader.remove_torrent(info_hash, remove_files=True)
                    
                    self._save_tasks()
            
            except Exception as e:
                logger.error(f"Error checking download {info_hash}: {str(e)}")
    
    def run_scheduler(self):
        """運行定時任務排程"""
        # 初始運行一次
        self.process_pending_tasks()
        self.check_downloads()
        
        # 設定定時任務
        schedule.every(CHECK_INTERVAL).seconds.do(self.process_pending_tasks)
        schedule.every(CHECK_INTERVAL).seconds.do(self.check_downloads)
        
        logger.info(f"Scheduler started, checking every {CHECK_INTERVAL} seconds")
        
        # 運行排程
        while True:
            schedule.run_pending()
            time.sleep(1)

def authenticate_onedrive():
    """運行 OneDrive 驗證流程"""
    uploader = OneDriveUploader(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        tenant_id=TENANT_ID,
        redirect_uri=REDIRECT_URI,
        scopes=SCOPES
    )
    
    if uploader.authenticate():
        print("OneDrive authentication successful!")
        return True
    else:
        print("OneDrive authentication failed!")
        return False

def main():
    """主函數"""
    parser = argparse.ArgumentParser(description='BT下載並上傳到OneDrive服務')
    subparsers = parser.add_subparsers(dest='command', help='命令')
    
    # 驗證命令
    auth_parser = subparsers.add_parser('auth', help='驗證 OneDrive')
    
    # 添加任務命令
    add_parser = subparsers.add_parser('add', help='添加下載任務')
    add_parser.add_argument('source', help='種子檔案路徑或磁力連結')
    
    # 檢視任務命令
    list_parser = subparsers.add_parser('list', help='列出所有任務')
    
    # 啟動服務命令
    start_parser = subparsers.add_parser('start', help='啟動服務')
    
    args = parser.parse_args()
    
    # 處理命令
    if args.command == 'auth':
        authenticate_onedrive()
    
    elif args.command == 'add':
        service = BTOneDriveService()
        if service.add_task(args.source):
            print(f"任務已添加: {args.source}")
        else:
            print(f"添加任務失敗，可能已存在: {args.source}")
    
    elif args.command == 'list':
        service = BTOneDriveService()
        tasks = service.tasks
        
        print("\n待處理任務:")
        for task in tasks.get('pending', []):
            print(f"  - {task.get('source')} (添加時間: {time.ctime(task.get('added_time', 0))})")
        
        print("\n下載中任務:")
        for info_hash, task in tasks.get('downloading', {}).items():
            status = task.get('status', {})
            progress = status.get('progress', 0)
            name = status.get('name', info_hash)
            print(f"  - {name} ({progress:.2f}%) - Hash: {info_hash}")
        
        print("\n已完成任務:")
        for task in tasks.get('completed', []):
            source = task.get('source', 'Unknown')
            status = task.get('status', {})
            name = status.get('name', 'Unknown')
            complete_time = task.get('complete_time', 0)
            print(f"  - {name} (來源: {source}, 完成時間: {time.ctime(complete_time)})")
        
        print("\n失敗任務:")
        for task in tasks.get('failed', []):
            source = task.get('source', 'Unknown')
            error = task.get('error', 'Unknown error')
            print(f"  - {source} (錯誤: {error})")
    
    elif args.command == 'start':
        service = BTOneDriveService()
        
        # 檢查 OneDrive 身份驗證
        if not service.uploader.is_authenticated():
            print("OneDrive 尚未驗證，正在嘗試驗證...")
            if not service.uploader.authenticate():
                print("Error: OneDrive 驗證失敗，請先運行 'auth' 命令")
                return
        
        print("BT OneDrive 服務啟動中...")
        service.run_scheduler()
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main() 