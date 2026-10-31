# 本地開發與驗證

先依 [backend README](../README.md) 安裝與啟動。Python 版本以 `.python-version` 為準；套件安裝沿用 requirements-dev.txt，未更換套件管理方式。
前端另於 frontend 執行 `npm ci`、`npm run dev`；Vite 將 `/api` 代理到 `127.0.0.1:8000`。

API 啟動入口已改為 `app.main:app`。試穿須同時啟動 `manage.py try-on-worker`。
若要從 FastAPI 預覽 React，先在 frontend 執行 `npm run build`；FastAPI 讀取 frontend/dist。正式前端部署於 Vercel。

## 測試

從 backend 執行：

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
$env:RUN_DATABASE_TESTS = '1'
.venv/Scripts/python.exe -m unittest discover -s tests -v
Remove-Item Env:RUN_DATABASE_TESTS
```

預設略過外部整合測試。RDS 測試需要連線及讀寫權限，大部分測試以交易回滾清理；部分照片測試也會存取私人 S3。
`RUN_FIREBASE_TESTS=1` 另啟真實 Firebase 測試；`RUN_VERTEX_LIVE_TEST` 為付費生成測試，日常整理與回歸不需開啟。
驗證輸出放 `var/verification/`，此目錄不進 Git。

檢查 `/api/health`（不依賴 DB）、`/api/health/db`（實際連線）、`/docs`。
Windows 沙箱若造成 TestClient 停滯，可在一般本地終端執行測試。
