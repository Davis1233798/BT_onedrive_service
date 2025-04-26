import os
import time
import logging
from transmission_rpc import Client
from tqdm import tqdm

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('bt_downloader')

class BTDownloader:
    def __init__(self, download_dir, max_download_rate=0, max_upload_rate=50):
        """
        初始化 BT 下載器
        
        Args:
            download_dir (str): 下載目錄
            max_download_rate (int): 最大下載速率 (KB/s), 0表示無限制
            max_upload_rate (int): 最大上傳速率 (KB/s)
        """
        self.download_dir = download_dir
        self.max_download_rate = max_download_rate  # KB/s
        self.max_upload_rate = max_upload_rate  # KB/s
        self.handles = {}  # 保存種子處理器的字典
        
        # 確保下載目錄存在
        os.makedirs(download_dir, exist_ok=True)
        
        # 連接到 Transmission，假設它運行在本地
        # 注意：需要先安裝和設定 Transmission
        try:
            self.session = Client(
                host='localhost',
                port=9091,
                username='',  # 如果設置了認證，則填寫
                password=''   # 如果設置了認證，則填寫
            )
            
            # 設置全局下載和上傳限制
            if max_download_rate > 0:
                self.session.set_session(
                    speed_limit_down=self.max_download_rate,
                    speed_limit_down_enabled=True
                )
            
            if max_upload_rate > 0:
                self.session.set_session(
                    speed_limit_up=self.max_upload_rate,
                    speed_limit_up_enabled=True
                )
            
            logger.info("BT session initialized with download_rate: %s, upload_rate: %s", 
                        max_download_rate, max_upload_rate)
        except Exception as e:
            logger.error(f"Error connecting to Transmission: {str(e)}")
            raise
    
    def add_torrent(self, torrent_path_or_magnet):
        """
        添加種子或磁力連結到下載佇列
        
        Args:
            torrent_path_or_magnet (str): 種子檔案路徑或磁力連結
            
        Returns:
            str: 種子信息哈希作為唯一ID
        """
        try:
            if torrent_path_or_magnet.startswith('magnet:'):
                # 處理磁力連結
                torrent = self.session.add_torrent(
                    torrent=torrent_path_or_magnet,
                    download_dir=self.download_dir
                )
                logger.info("Adding magnet link: %s", torrent_path_or_magnet[:60] + "...")
            else:
                # 處理種子檔案
                with open(torrent_path_or_magnet, 'rb') as f:
                    torrent_data = f.read()
                    
                torrent = self.session.add_torrent(
                    torrent=torrent_data,
                    download_dir=self.download_dir
                )
                logger.info("Adding torrent file: %s", torrent_path_or_magnet)
            
            info_hash = torrent.hashString
            self.handles[info_hash] = torrent.id
            
            logger.info("Torrent added with info hash: %s", info_hash)
            return info_hash
            
        except Exception as e:
            logger.error("Error adding torrent: %s", str(e))
            raise
    
    def get_torrent_status(self, info_hash):
        """
        獲取種子下載狀態
        
        Args:
            info_hash (str): 種子信息哈希
            
        Returns:
            dict: 種子狀態信息
        """
        if info_hash not in self.handles:
            return {"error": "Torrent not found"}
        
        torrent_id = self.handles[info_hash]
        torrent = self.session.get_torrent(torrent_id)
        
        # 計算下載進度
        progress = torrent.progress
        
        # 獲取檔案列表
        files = [f.name for f in torrent.files()]
        
        return {
            "info_hash": info_hash,
            "name": torrent.name,
            "progress": progress,
            "download_rate": torrent.rate_download / 1024,  # KB/s
            "upload_rate": torrent.rate_upload / 1024,  # KB/s
            "state": torrent.status,
            "num_peers": torrent.peers_connected,
            "is_finished": progress >= 99.9,
            "files": files,
            "save_path": self.download_dir
        }
    
    def wait_for_download(self, info_hash, progress_bar=True):
        """
        等待種子下載完成
        
        Args:
            info_hash (str): 種子信息哈希
            progress_bar (bool): 是否顯示進度條
            
        Returns:
            dict: 完成的下載信息
        """
        if info_hash not in self.handles:
            return {"error": "Torrent not found"}
        
        torrent_id = self.handles[info_hash]
        pbar = None
        
        if progress_bar:
            pbar = tqdm(total=100, desc="Downloading")
        
        last_progress = 0
        while True:
            torrent = self.session.get_torrent(torrent_id)
            progress = torrent.progress
            
            if progress_bar and progress > last_progress:
                pbar.update(progress - last_progress)
                last_progress = progress
            
            # 檢查是否完成
            if progress >= 99.9:
                if progress_bar:
                    pbar.close()
                
                # 等待做種
                time.sleep(3)
                
                result = self.get_torrent_status(info_hash)
                logger.info("Download completed: %s", result["name"])
                return result
            
            time.sleep(1)
    
    def get_download_path(self, info_hash):
        """
        獲取下載檔案的完整路徑
        
        Args:
            info_hash (str): 種子信息哈希
            
        Returns:
            str: 下載檔案或目錄的路徑
        """
        if info_hash not in self.handles:
            return None
        
        torrent_id = self.handles[info_hash]
        torrent = self.session.get_torrent(torrent_id)
        
        # 獲取檔案列表
        files = torrent.files()
        
        # 如果只有一個檔案，返回檔案路徑
        if len(files) == 1:
            file_path = os.path.join(self.download_dir, torrent.name)
            return file_path
        
        # 如果是多個檔案，返回目錄路徑
        return os.path.join(self.download_dir, torrent.name)
    
    def remove_torrent(self, info_hash, remove_files=False):
        """
        移除種子
        
        Args:
            info_hash (str): 種子信息哈希
            remove_files (bool): 是否同時刪除已下載的檔案
            
        Returns:
            bool: 操作是否成功
        """
        if info_hash not in self.handles:
            return False
        
        torrent_id = self.handles[info_hash]
        torrent = self.session.get_torrent(torrent_id)
        name = torrent.name
        
        # 從會話中移除種子
        self.session.remove_torrent(torrent_id, delete_data=remove_files)
        
        # 從字典中移除引用
        del self.handles[info_hash]
        
        logger.info("Removed torrent: %s (remove_files=%s)", name, remove_files)
        return True 