# KINU TABI FastAPI 後端

React 前端位於 `../frontend`。後端採依功能分組的分層架構，保留原有 SQL、資料表、API 與商業規則。

## 開始開發

從 backend 執行：

```powershell
uv venv --python 3.13
uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

已有 `.venv` 可略過建立步驟。環境變數沿用 `backend/.env`，範例見 `.env.example`；啟動不會自動建表或 seed。
AI 試穿另開終端執行 `.venv/Scripts/python.exe manage.py try-on-worker`。
API 文件：<http://127.0.0.1:8000/docs>。

## 文件

- [架構與資料夾責任](docs/architecture.md)
- [開發與測試](docs/development.md)
- [維護與資料初始化](docs/operations.md)
- [部署](docs/deployment.md)
- [前後端整合與商業規則](../INTEGRATION.md)
- [功能設定參考與歷史文件](docs/README.md)
