# 資料夾整理驗證

日期：2026-10-23。

- OpenAPI 與整理前快照完全一致，包含 33 個公開文件路徑的契約。
- migrations 與圖片共 23 個檔案的 SHA-256 完全一致。
- 所有 app 與 commands 模組可匯入，未依賴舊平面模組。
- 一般測試：59 項中 23 通過、36 項外部測試略過。
- 開啟 RUN_DATABASE_TESTS 的完整回歸：59 項中 55 通過、4 略過，耗時約 426 秒。
- 略過：真實 Firebase、兩項真實 S3、付費 Vertex 生成；AI SDK 與 worker 使用模擬服務驗證。
- 本機 HTTP：health、DB health、plans、models、React plans 頁面均回應 200。
- git diff --check 通過；未新增套件、未執行 migration 或 seed。

完整測試輸出位於本地 var/verification/backend-refactor-tests.log，不進 Git。
API 已以 app.main:app 重新啟動，背景 worker 沿用 manage.py try-on-worker。
測試既有 httpx／Starlette deprecation warning 保留，本次不更換依賴版本。
