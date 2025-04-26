import os
import time
import libtorrent as lt
from tqdm import tqdm
import logging

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
        self.max_download_rate = max_download_rate * 1024  # 轉換為 bytes
        self.max_upload_rate = max_upload_rate * 1024  # 轉換為 bytes
        self.session = None
        self.handles = {}  # 保存種子處理器的字典
        
        # 確保下載目錄存在
        os.makedirs(download_dir, exist_ok=True)
        
        self._init_session()
    
    def _init_session(self):
        """初始化 libtorrent 會話"""
        self.session = lt.session()
        settings = {
            'alert_mask': lt.alert.category_t.all_categories,
            'enable_dht': True,
            'announce_to_dht': True,
            'enable_lsd': True,
            'enable_natpmp': True,
            'enable_upnp': True,
            'download_rate_limit': self.max_download_rate,
            'upload_rate_limit': self.max_upload_rate
        }
        self.session.apply_settings(settings)
        logger.info("BT session initialized with settings: %s", settings)
    
    def add_torrent(self, torrent_path_or_magnet):
        """
        添加種子或磁力連結到下載佇列
        
        Args:
            torrent_path_or_magnet (str): 種子檔案路徑或磁力連結
            
        Returns:
            str: 種子信息哈希作為唯一ID
        """
        params = {
            'save_path': self.download_dir,
            'storage_mode': lt.storage_mode_t.storage_mode_sparse
        }
        
        if torrent_path_or_magnet.startswith('magnet:'):
            # 處理磁力連結
            params['url'] = torrent_path_or_magnet
            logger.info("Adding magnet link: %s", torrent_path_or_magnet[:60] + "...")
        else:
            # 處理種子檔案
            params['ti'] = lt.torrent_info(torrent_path_or_magnet)
            logger.info("Adding torrent file: %s", torrent_path_or_magnet)
        
        handle = self.session.add_torrent(params)
        info_hash = str(handle.info_hash())
        self.handles[info_hash] = handle
        
        logger.info("Torrent added with info hash: %s", info_hash)
        return info_hash
    
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
        
        handle = self.handles[info_hash]
        status = handle.status()
        
        # 獲取檔案路徑
        files = []
        if handle.has_metadata():
            torrent_info = handle.get_torrent_info()
            for i in range(torrent_info.files().num_files()):
                file_info = torrent_info.files().file_path(i)
                files.append(file_info)
        
        # 計算下載進度
        progress = status.progress * 100
        
        return {
            "info_hash": info_hash,
            "name": handle.name() if handle.has_metadata() else "Unknown",
            "progress": progress,
            "download_rate": status.download_rate / 1024,  # KB/s
            "upload_rate": status.upload_rate / 1024,  # KB/s
            "state": str(status.state),
            "num_peers": status.num_peers,
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
        
        handle = self.handles[info_hash]
        pbar = None
        
        if progress_bar:
            pbar = tqdm(total=100, desc="Downloading")
        
        last_progress = 0
        while True:
            status = handle.status()
            progress = status.progress * 100
            
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
        
        handle = self.handles[info_hash]
        
        if not handle.has_metadata():
            return None
        
        status = self.get_torrent_status(info_hash)
        
        # 如果只有一個檔案，返回檔案路徑
        if handle.get_torrent_info().files().num_files() == 1:
            file_path = os.path.join(self.download_dir, handle.name())
            return file_path
        
        # 如果是多個檔案，返回目錄路徑
        return os.path.join(self.download_dir, handle.name())
    
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
        
        handle = self.handles[info_hash]
        name = handle.name() if handle.has_metadata() else info_hash
        
        # 從會話中移除種子
        remove_option = lt.session.delete_files if remove_files else lt.session.none
        self.session.remove_torrent(handle, remove_option)
        
        # 從字典中移除引用
        del self.handles[info_hash]
        
        logger.info("Removed torrent: %s (remove_files=%s)", name, remove_files)
        return True 