# BT OneDrive 下載服務

一個自動下載 BT 種子/磁力連結並上傳至 OneDrive 的服務。這個應用程式可以在本地運行，也可以部署在 GitHub Actions 上。

## 功能特點

- 支援 BT 種子檔案和磁力連結下載
- 自動上傳完成的下載內容到 OneDrive
- 任務管理和狀態追蹤
- 可運行在本地或 GitHub Actions 上
- 靈活的配置選項

## 安裝需求

- Python 3.7+
- libtorrent 庫 (用於 BT 下載)
- Microsoft 帳號 (用於 OneDrive 存取)

## 安裝步驟

1. 克隆此倉庫:
   ```bash
   git clone https://github.com/yourusername/bt-onedrive-service.git
   cd bt-onedrive-service
   ```

2. 安裝 libtorrent 依賴:
   - Ubuntu/Debian:
     ```bash
     sudo apt-get install python3-libtorrent
     ```
   - Windows:
     ```bash
     pip install libtorrent
     ```
   - macOS:
     ```bash
     brew install libtorrent-rasterbar
     pip install libtorrent
     ```

3. 安裝其他依賴:
   ```bash
   pip install -r requirements.txt
   ```

4. 創建配置檔:
   ```bash
   cp env.example .env
   ```

5. 編輯 `.env` 檔案，填入你的 OneDrive API 認證資訊。

## OneDrive API 設定

要使用此應用程式，你需要在 Microsoft Azure 應用程式平台註冊一個應用程式:

1. 訪問 [Azure 應用程式註冊頁面](https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade)
2. 點擊「新增註冊」
3. 輸入應用程式名稱，例如「BT OneDrive Service」
4. 選擇支援的帳戶類型 (建議選擇「任何組織目錄中的帳戶」)
5. 設定重定向 URI 為 `http://localhost:8000/callback`
6. 註冊應用程式
7. 註冊後，記下「應用程式(客戶端) ID」
8. 在「憑證和密碼」分頁中，建立新的客戶端密碼，並記下值

將這些值填入 `.env` 檔案:

```
ONEDRIVE_CLIENT_ID=your_client_id_here
ONEDRIVE_CLIENT_SECRET=your_client_secret_here
```

## 使用方法

### 初始認證

首次使用前，需要進行 OneDrive 認證:

```bash
python main.py auth
```

這將顯示一個設備代碼和一個 URL。訪問 URL，登入 Microsoft 帳號，並輸入設備代碼以授權應用程式。

### 添加下載任務

添加 BT 種子或磁力連結下載任務:

```bash
python main.py add "magnet:?xt=urn:btih:..."
# 或
python main.py add "/path/to/your/torrent/file.torrent"
```

### 查看任務清單

列出所有任務及其狀態:

```bash
python main.py list
```

### 啟動服務

啟動下載和上傳服務:

```bash
python main.py start
```

服務會定期檢查下載狀態，並在下載完成後自動上傳到 OneDrive。

## 部署在 GitHub Actions

要在 GitHub Actions 上部署此服務:

1. Fork 此倉庫到你的 GitHub 帳號

2. 在倉庫設定中添加以下 Secrets:
   - `ONEDRIVE_CLIENT_ID`: 你的 Azure 應用程式 ID
   - `ONEDRIVE_CLIENT_SECRET`: 你的 Azure 應用程式密碼
   - `ONEDRIVE_TOKEN` (可選): 如果你已經有認證 token，可以添加它以跳過認證步驟

3. 使用 GitHub 的 Actions 頁面手動觸發工作流程，並輸入磁力連結或種子 URL

4. GitHub Actions 將自動下載內容並上傳到你的 OneDrive

## 配置選項

你可以在 `.env` 檔案中自定以下設定:

- `DOWNLOAD_DIR`: 下載目錄路徑
- `MAX_DOWNLOAD_RATE`: 最大下載速率 (KB/s, 0表示無限制)
- `MAX_UPLOAD_RATE`: 最大上傳速率 (KB/s)
- `ONEDRIVE_UPLOAD_FOLDER`: OneDrive 上傳目標資料夾
- `CHECK_INTERVAL`: 檢查下載狀態的間隔 (秒)

## 常見問題

**Q: 我在 GitHub Actions 上使用時遇到認證問題?**

A: GitHub Actions 運行在無頭環境中，最好提前獲取 `onedrive_token.json` 檔案，並通過 Secrets 傳遞給工作流程。

**Q: 如何增加 GitHub Actions 的運行時間?**

A: 在 `.github/workflows/bt_download.yml` 檔案中修改 `timeout` 值以延長運行時間。注意 GitHub Actions 免費版有時間限制。

**Q: 下載完成後，檔案會自動刪除嗎?**

A: 默認情況下，檔案不會自動刪除。如需啟用自動刪除，請修改 `main.py` 中的 `check_downloads` 方法，取消註釋 `self.downloader.remove_torrent(info_hash, remove_files=True)` 這一行。

## 授權

本專案使用 MIT 授權。詳見 [LICENSE](LICENSE) 檔案。

## 免責聲明

請確保你只下載你有合法權利下載的內容。作者不對此工具的使用負任何法律責任。 