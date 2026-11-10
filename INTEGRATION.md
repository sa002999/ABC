# React／FastAPI 整合

本文件是整合後的啟動與規則依據。`frontend/docs/step-*-progress.md` 是匯入前 React 專案的歷史紀錄。2026-11-07 官網已另行完成 Sandbox 付款與測試預約，現行狀態見 [付款文件](backend/docs/payments.md)。

## 目錄

- `frontend/`：正式開發的 React 19、TypeScript、Vite、Tailwind 前端。
- `backend/`：沿用 FastAPI、RDS PostgreSQL、Firebase、私人 S3 與 Vertex AI worker。
- `frontend-legacy/`：替換前的原生前端備份，不作為網站入口。
- 同層原始 `kinu-tabi-react/` 保留，不是後續修改入口。

## 本機啟動

在三個 PowerShell 終端執行。第一次安裝前端套件使用 `npm ci`；後續啟動不需重裝。

API（既有環境直接啟動；migration 與 seed 只在初始化或新增版本時明確執行）：

```powershell
cd "D:\OneDrive\Jessica Documents\wehelp_stage3\P_Kinu-Tabi\backend"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

背景工作（AI 任務、生成圖清理、過期暫留清理）：

```powershell
cd "D:\OneDrive\Jessica Documents\wehelp_stage3\P_Kinu-Tabi\backend"
.\.venv\Scripts\python.exe manage.py try-on-worker
```

前端：

```powershell
cd "D:\OneDrive\Jessica Documents\wehelp_stage3\P_Kinu-Tabi\frontend"
npm ci
npm run dev
```

開啟 <http://127.0.0.1:5173>。Vite 將 `/api` 代理至 `127.0.0.1:8000`，不要直接開啟 HTML。

也可在前端執行 `npm run build`，由 FastAPI 在 <http://127.0.0.1:8000> 提供 `frontend/dist`；更新程式後須重新建置。SPA 子路由可直接開啟或重新整理；舊 `/#/plans` 網址會轉成 `/plans`。

後端資料夾與維護方式見 [後端文件](backend/README.md)。

## 設定

- `frontend/.env.local`：Firebase 公開 Web 設定，專案為 **kinu-tabi**；本機 `VITE_API_BASE_URL` 留空，使用 Vite 代理。
- `backend/.env`：保留現有資料庫、Firebase Admin、AWS 與 Vertex 設定；不將私人憑證放入 `VITE_*`。
- 後端 `CORS_ORIGINS` 預設僅允許兩個本機 5173 來源。正式環境須明確設定 Vercel 的 HTTPS 網址。
- S3 已支援 8000 的直傳來源。5173 若未設定 S3 CORS，後端提供受登入、同意、大小及持有權檢查的 API 上傳備援；仍儲存於私人 S3，沿用同一套照片驗證流程。現有 AWS 身分沒有管理 bucket CORS 的權限，本次未更改 AWS 存取權限或 bucket CORS。
- `manage.py check-react` 可檢查 Firebase 專案與開發上傳來源。

## 已確認的商業規則

1. 每筆限 1～3 名成人；不提供兒童方案。和服不分尺寸，每件實體庫存有獨立編號。
2. 單人方案按人計價；情侶套餐必須包含一女一男，占用兩個接待名額與兩件和服，套餐底價只計一次。第三位依套餐設定的單人加價計費。
3. 女生可加選一條收費腰帶，分類為配件；男生不可選腰帶或其他配件。腰帶保存於收藏及後端預約草稿，現階段不作逐件實體庫存暫留。
4. 金額一律為 TWD 非負整數，由後端目錄計算。前端搭配小計、收藏即時價格、報價及暫留遵守相同計價。價格變動後拒絕沿用舊報價。
5. 開始前至少 24 小時至未來 90 天，使用日本時間。報價不占庫存；明確確認報價後才整筆暫留 10 分鐘。任何人的和服或名額不足，整筆失敗。
6. 暫留重送使用相同冪等識別碼，不能延長期限。暫留可釋放，尚不代表付款或正式預約成立。
7. 聯絡資料保存在會員後端草稿，瀏覽器儲存空間不保存聯絡資料。跨頁暫存只使用頁面記憶體；重整後由伺服器恢復草稿與原暫留。
8. 本人照片與模特兒來源可重用；照片處理同意與每次生成確認分開。原圖、生成圖、收藏分開管理；保留會員隔離、版本衝突與生成額度限制。
9. 官網支援 TapPay Sandbox 非 3D 信用卡、正式測試預約及會員查詢；正式收款、攝影加購、退款執行、票券、刪帳與後台營運操作尚未開放。AI／MCP 進度另見各模組現行文件。

付款另執行 `backend/.venv/Scripts/python.exe backend/manage.py payment-reconcile`（或在 backend 執行 `.venv/Scripts/python.exe manage.py payment-reconcile`）；詳見付款文件的啟動與驗收說明。

## 示範價格

單人方案 NT$1,500／1,800／2,100；情侶套餐 NT$2,800，第三位 NT$1,500。素色腰帶 NT$200、花紋腰帶 NT$350。

例如情侶＋第三位＋一條素色腰帶：2,800＋1,500＋200＝**NT$4,500**。兩位套餐旅客各分配不同實體和服，第三位再分配一件。

`010_react_packages.sql` 新增套餐與腰帶結構；`011_demo_packages.sql` 設定開發商品及兩店示範庫存。既有移除尺寸的 `009` 遷移沿用。商品圖片與性別分類目前均為開發示範，不表示正式商品或庫存建檔完成。

## 驗證

```powershell
# frontend
npm test
npm run build

# backend：一般測試
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

# backend：使用現有開發資料庫的整合測試
$env:RUN_DATABASE_TESTS='1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
Remove-Item Env:RUN_DATABASE_TESTS
```

RDS 測試大多使用交易回滾；庫存並行測試建立自己的測試資料，結束時清除。Firebase、真實 S3 與付費 Vertex 測試各有獨立 opt-in，不會因啟用 RDS 測試而呼叫付費 AI。

## Vercel／EC2 部署準備

1. Vercel 的專案根目錄設為 `frontend`，建置指令 `npm run build`，輸出 `dist`。
2. 設定 Vercel 的 Firebase 公開環境變數，並將 `VITE_API_BASE_URL` 設為 EC2 API 的 HTTPS 網域，末尾不加 `/api`；改完環境變數需重新建置。
3. EC2 設定私人後端環境變數，部署 API 與持續執行的 worker。使用 HTTPS 反向代理，明確設定 `CORS_ORIGINS` 為正式前端來源。
4. Firebase 設定正式前端 Authorized domains 及驗證／重設信返回網址。若要 S3 直傳，可由具有權限的人加入正式前端來源；否則使用受驗證的 API 上傳路徑。
5. 雲端上線前再驗收登入、照片、worker、庫存與 HTTPS。此次整合僅完成本機開發，不會自動發布至 Vercel 或 EC2。
