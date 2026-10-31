# 部署方向

前端：Vercel，專案根目錄 frontend，Vite build，輸出 dist。
後端：AWS EC2，部署 backend 與其 data、migrations，建立 Python 環境並安裝 requirements.txt。
人物照片驗證程式位於 `app/modules/try_on/pose_check.py`，部署需包含 `data/ml-models/pose_landmarker_lite.task`（目前提供的 Lite 模型約 5.8 MB）。模型透過 `DATA_DIR` 定位，從本機載入，不在使用者上傳時下載；缺少模型或 MediaPipe 無法執行時，新照片驗證回 503，不直接放行。既有照片與預設模特兒不補驗證。

在 backend 工作目錄執行：

```sh
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
python manage.py try-on-worker
```

API 與 worker 應由程序管理工具各自管理；正式環境不使用 --reload。EC2 前方配置 HTTPS 反向代理，秘密由執行環境提供。
設定 CORS_ORIGINS 為實際 Vercel 網域，前端 VITE_API_BASE_URL 指向後端 HTTPS 網址，並確認 Firebase authorized domains 與私人 S3 上傳 CORS。
部署前明確執行 migration；不在 HTTP 啟動時自動執行。不需要將開發 seed 自動帶入部署。

目前是部署規劃，這次資料夾整理未建立或發布 Vercel／EC2 資源。TapPay Sandbox 屬下一階段。
