# 本地後端開發

目前以 FastAPI 提供 API，React 前端位於 ../frontend。啟動、整合規則與部署請以 [整合說明](../INTEGRATION.md) 為準。本地程式讀取 `backend/.env`，資料庫連到目前設定的 AWS RDS PostgreSQL。現階段使用 `DATABASE_URL`；S3 與 CloudFront 已接入商品圖片，會員照片與試穿結果使用私人 S3。`DATABASE_SECRET_ID` 尚未實作讀取。

從 `backend` 資料夾執行以下 PowerShell 指令，不必先啟用虛擬環境：

```powershell
uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt
.venv/Scripts/python.exe manage.py check
.venv/Scripts/python.exe manage.py migrate
.venv/Scripts/python.exe manage.py seed-demo
.venv/Scripts/python.exe -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

`migrate` 使用交易及遷移紀錄，重跑不重建資料表。`seed-demo` 只新增兩筆帶 `is_demo=true` 的測試門市，重跑不覆寫正式資料；沒有假地址、座標或營業時間。HTTP 啟動時不自動建表或寫入測試資料。

開啟 `http://127.0.0.1:8000/#/stores` 查看門市。需從此網址開啟前端，讓 `fetch('/api/stores')` 使用同一個來源；直接開啟 HTML 檔案無法存取 API。啟動程式後可在 `http://127.0.0.1:8000/docs` 操作 OpenAPI 文件。

API：

- `GET /api/health`：程式是否可用，不依賴資料庫。
- `GET /api/health/db`：實際檢查 PostgreSQL 連線，不回傳連線設定。
- `GET /api/stores`：僅列出啟用門市，支援 `?city=TOKYO` 或 `?city=KYOTO`。
- `GET /api/stores/{UUID}`：查詢啟用門市；不存在或下架回 404。

門市列表格式為 `{ "data": [...] }`。名稱及地址使用語系字典；前端優先顯示繁中。資料欄位含 `openingHours`、`isDemo`，測試資料在畫面中顯示標記。錯誤使用統一 `error` 格式及請求識別碼，不回傳資料庫錯誤細節。

本地需能連線到 RDS 的 PostgreSQL 連接埠，並具有目前資料庫的建表與讀寫權限；程式不會修改 AWS 安全群組。預設要求加密連線；若 URL 已設定 `verify-full` 等模式，程式會沿用。連線與 SQL 查詢均設逾時。

驗證：

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
$env:RUN_DATABASE_TESTS = '1'
.venv/Scripts/python.exe -m unittest discover -s tests -v
Remove-Item Env:RUN_DATABASE_TESTS
```

第一個指令不存取 RDS。第二次會驗證 RDS、城市篩選、門市詳情與下架資料不可公開；下架測試資料以回滾交易清除。

商品與方案目錄已完成，包含和服資料、商品圖、方案、門市關聯與前端篩選／詳情。初始化與 API 規格見 [CATALOG.md](CATALOG.md)。Firebase 會員與造型收藏操作說明見 [AUTH.md](AUTH.md) 與 [LOOKS.md](LOOKS.md)。試穿及預約草稿／庫存暫留見下方專章；正式付款、預約成立與票券仍待實作，不能以線框或暫留代替。

## Firebase 會員

註冊、登入、驗證與重設密碼的操作與測試方式，請見 [AUTH.md](AUTH.md)。

## AI 試穿人物來源

預設模特兒與本人照片上傳、替換、刪除及來源重用已接入。初始化、私人儲存與維護方式見 [PHOTO_SETUP.md](PHOTO_SETUP.md)。人物品質自動判斷延後整合。

AI 試穿的生成任務、確認與每日額度、私人結果與生成圖收藏已接入；啟動時須同時執行 API 與 `manage.py try-on-worker`。Google Cloud 權限設定與真實生成驗收狀態見 [TRY_ON.md](TRY_ON.md)。人物品質自動判斷仍延後。

## 預約草稿與庫存

七步驟預約草稿、門市即時名額、逐件庫存、TWD 報價與整筆 10 分鐘暫留已接入。資料初始化、測試設定與 API 見 [BOOKING.md](BOOKING.md)。到期清理沿用現有 worker；更新後請同時重啟 API 與 worker。TapPay、正式預約與票券尚未開放。
