# AI 和服試穿

## 本機啟動

資料庫 migration 007 已於本次開發套用。其他環境先執行 `manage.py migrate`。

在 backend 目錄開啟兩個終端機：

```powershell
# 終端機 1：網站與 API；可沿用你原本可使用的埠。
.venv/Scripts/python.exe -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

```powershell
# 終端機 2：持續處理已確認的試穿任務，保持執行。
.venv/Scripts/python.exe manage.py try-on-worker
```

沒有啟動 worker 時，任務保留在資料庫並顯示排隊中。重新整理頁面或查詢結果不會重新生成；worker 啟動後接續處理排隊任務。worker 每 3 秒取件，以 PostgreSQL 鎖避免不同程序重複取件，不需 Redis 或另一套佇列服務。EC2 上線時應將 API 與 worker 分別設為受管理的服務。

## Google Cloud 設定

使用 `google-genai==2.31.0`，依既有 `try_on.py` 的 `genai.Client` → `models.recontext_image`、`RecontextImageSource`、`ProductImage` 與 `RecontextImageConfig(number_of_images=1)` 流程呼叫。人物與服裝從私人儲存取得後以 `types.Image(image_bytes=..., mime_type='image/jpeg')` 傳入相同結構，不額外落地會員原圖。SDK 明確設定 Vertex、專案與地區，逾時 180 秒、總嘗試數 1，避免自動重送付費預測。

`.env` 的 `GOOGLE_CLOUD_PROJECT`、`GOOGLE_CLOUD_LOCATION` 指定 Vertex 專案與地區。本機使用既有 `gcloud` ADC；Firebase 的 JSON 路徑已改為專用 `FIREBASE_SERVICE_ACCOUNT_PATH`，由 Firebase Admin 明確載入，不再佔用 Google 的全域 ADC 變數。

EC2 可設定 `GOOGLE_APPLICATION_CREDENTIALS` 指向具 Vertex 權限的服務帳戶 JSON 或使用適用的工作負載身分。這與 Firebase 的服務帳戶分開；私鑰不可提交版本庫。若本機尚未建立 ADC，先完成 `gcloud auth application-default login`。

可選參數：`VERTEX_TRY_ON_MODEL`（預設 `virtual-try-on-001`）、`VERTEX_TRY_ON_LOCATION`（未設定時沿用 Google Cloud 地區）。不讀取前端提供的供應商網址或模型名稱。

若部署 EC2 改用服務帳戶，才在 Vertex 所屬專案 IAM，為該 Vertex 憑證 JSON 的 `client_email` 授予：

- Vertex AI User：`roles/aiplatform.user`。
- Service Usage Consumer：`roles/serviceusage.serviceUsageConsumer`。

同時啟用 Vertex AI API 與專案帳務。Firebase 管理權限不代表已取得另一個 Google Cloud 專案的預測權限。

首次 REST 驗證誤用了 `.env` 的 Firebase 服務帳戶，回傳 HTTP 403；該帳戶在 Vertex 專案沒有預測權限。已依使用者要求改為 Google Gen AI SDK，並分離 Firebase 憑證與本機 gcloud ADC。不要因先前 Firebase 帳戶的 403 就直接擴大其權限；應先以正確的 Vertex 憑證重新驗證。請勿將服務帳戶 JSON 或 access token 貼到前端或日誌。

2026-10-17：改用 SDK 與本機 gcloud ADC 後，真實單張生成已通過（預設模特兒 1＋紫藤花語和服）；不需要新增前述 Firebase 帳戶的 Vertex IAM 權限。已檢視結果確實為該人物穿著和服，原始參考 `try_on.py` 保持原樣。

官方參考：[Virtual Try-On 生成指南](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/generate-virtual-try-on-images)。

## 操作與額度

1. 登入，從 AI 試穿頁選擇方案及人物來源。
2. 按「準備生成確認」查看人物、方案、用途與額度說明。
3. 按「確認生成（使用 1 次）」才建立任務並傳送至 Vertex。取消不扣次；選圖、換衣、查詢與收藏不會生成。
4. 顯示排隊／確認來源／生成中／完成或失敗；可離開後在「我的試穿紀錄」找回任務。
5. 成功後提供私人限時圖片、加入造型收藏及提前刪圖。收藏不保留庫存；圖片失效後搭配仍保留，改顯示商品圖。

網站穿搭與未來場景共用每日 5 個已確認任務；MCP 每日 3 個的資料欄位與回應分開，目前未開放 MCP 生成入口。依 `Asia/Tokyo` 午夜重設。每次建立任務即計次，失敗仍計入；重新確認產生新任務使用新鍵、再計 1 次。供應商呼叫嘗試數另外記錄，不用會員額度冒充 Google 實際費用。

`Idempotency-Key` 為必要 UUID。同會員同鍵同內容回原任務、不重扣；同鍵不同內容回 409。以會員資料列鎖與資料庫唯一約束處理跨裝置併發，同時只允許一個網站任務。瀏覽器只暫存擁有者範圍的任務 ID、選項與重送鍵，沒有照片、JWT 或圖片簽名 URL；網路失敗可重送同一次請求。

人物品質自動判斷依使用者決定延後。本人照須通過現有格式／大小／方向／EXIF 檢查且同意仍有效，畫面明示人物品質尚未檢查；不將其標為品質合格。派送至 Vertex 前重查來源與同意。已傳送的供應商請求無法因之後刪除原圖而收回；刪原圖不會刪除既有生成圖或收藏。

## 保存與故障處理

生成圖存於 `private/try-on/generations/`，不使用公開 CloudFront。圖片完成起保存 7 天，API 過期立即停止簽名，私人網址最長 120 秒且不超過圖片到期時間。刪圖立即停止 API 使用，再由 worker 清除 S3 全部版本；已簽發網址可能在其短效期限內仍有效。worker 同時定期清除到期、已刪與失敗殘留圖片。

程序中斷超過 15 分鐘的執行中任務標為失敗，不自動再次呼叫可能已收費的預測。逾時與供應商錯誤也不自動重生。失敗只保存可公開的錯誤代碼，供應商原始訊息、人物圖與 token 不寫日誌。成功上傳後若資料庫更新中斷，預先保存的物件路徑可供後續清除。

worker 停止期間，可手動清除到期與待刪物件：

```powershell
.venv/Scripts/python.exe manage.py cleanup-generations
```

正式部署須保持 worker 執行並監控清除失敗。S3 可另外設定僅針對 `private/try-on/generations/` 的保留期限作為備援；不要套用到本人原圖。

## API

- `GET /api/account/generation-usage`
- `POST /api/try-on/sessions/{sessionId}/generations`：原搭配＋photoId 或 modelId＋`confirmed:true`，需 Idempotency-Key。
- `GET /api/try-on/jobs/{jobId}`
- `GET /api/try-on/generations?page=0&pageSize=12`
- `DELETE /api/try-on/generations/{generationId}`
- `POST /api/looks`：可加入有效、本人所有且搭配相符的 generationId。

配件穿戴與場景合成仍為後續工作，不會以本次和服生成冒充完成。

## 測試

```powershell
$env:RUN_DATABASE_TESTS='1'
.venv/Scripts/python.exe -m unittest tests.test_generations -v
```

一般測試不呼叫付費 AI，資料庫測試以回滾交易清除。真實生成測試另需明確啟用 `RUN_VERTEX_LIVE_TEST=1`，執行 `tests.test_generations.VertexLiveTest`，每次會呼叫一次付費預測，使用提供的預設模特兒與和服，結果存於 `backend/verification/try-on-live.jpg`；測試結果不冒充會員生成任務。

`RUN_PHOTO_STORAGE_TESTS=1` 可另外執行 `GenerationIntegrationTests.test_real_result_storage_preview_and_cleanup`，重用上述已生成檔案，不再次呼叫 AI。2026-10-17 已驗證任務完成、私人 S3 JPEG 寫入、授權預覽與實際清除；測試物件已刪除，資料庫回滾。
