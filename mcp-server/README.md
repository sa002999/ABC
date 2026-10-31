# KINU TABI MCP Server

獨立 Node.js 服務，透過 HTTP 呼叫既有 FastAPI。產品定案見 [MCP_SPEC.md](../MCP_SPEC.md)。本目錄不直接連資料庫，不讀 backend/.env，不複製交易或生成規則。

## 目前範圍

目前提供公開目錄、逐人搭配、會員連線、AI 試穿及全員可用日期／時段，包含：

- `list_plans`：城市、成人總人數、關鍵字、排序與分頁。先取得城市與人數。partySize 是探索上下文，不當成後端方案篩選或全員可用性驗證。
- `get_plan_details`：依真實 UUID 重新查方案內容，沒有寫入選款或建立草稿。
- `show_plan_picker`：重新查公開方案，關聯 `ui://kinu-tabi/plan-picker-v5.html`。沒有 UI 的客戶端仍收到文字與 structuredContent；舊資源 URI 保留供既有連線讀取。
- `list_kimonos`、`get_kimono_details`：查真實方案適用和服與商品詳情。
- `check_outfit_summary`：將 1～3 位成人完整搭配送往 FastAPI，檢查套餐、款式與性別適用性，回傳估計金額與共同門市。
- `get_member_status`：驗證 HTTP 連線的本人 Bearer token。無任何 token 或 userId 工具參數。
- HTML 介面：圖文、計價單位、套餐人數規則、示範標記、查詢與點選。使用官方 MCP Apps App SDK 的 tools/call、updateModelContext、sendMessage。
- HTTP `/mcp` 及 stdio transport。`/health` 只回報程序存活，不代表 FastAPI 可用。

`check_party_availability` 與 `show_party_availability` 分別提供文字與日期／時段 UI。傳入 city、完整 guests、共同門市 storeId 與 from/to 日本日期（含首尾，最多 31 天），透過公開 `POST /api/catalog/party-availability` 重用後端預約規則，檢查全員接待名額、不同實體和服、租借／整備期間與關店限制。開始前至少 24 小時、最遠未來 90 天；所有顯示時間為 Asia/Tokyo。查詢逾時可重試，不會建立預約資料。

共同門市本身不代表日期有庫存。UI 更換搭配、門市、日期即清除舊結果與時段偏好；無可用時段時保留搭配供改查。選時段不保留庫存、不建立草稿，預約草稿與回站交易仍屬後續里程碑。選款 UI 進度只保留在目前 iframe；搜尋、切換城市或整團人數會重新開始。`show_party_availability` 可用明確全員搭配及日期恢復查詢介面，會重查現況。

本機服務啟動後，在本目錄執行 `node verify-availability.mjs`，可匿名驗證示範三人全員搭配、31天查詢與 v5 UI 資源；此驗證不建立預約，也不等於原生客戶端UI驗收。原生驗收請重新載入外掛工具並開啟新卡片，依「逐人選款 → 檢查搭配 → 選共同門市與日期 → 查詢 → 選時段」操作；再修改日期，確認舊結果及偏好清除、原搭配保留。

## AI 試穿

- `show_try_on`：需本人會員 token，依一位旅客的 planId／kimonoId 開啟 `ui://kinu-tabi/try-on-v4.html`（保留 v1～v3 資源相容）。可選適用性別的模特兒，或本人有效同意的照片庫照片。
- 新照片可直接在試穿介面按「新增本人照片」，本機選檔／預覽、閱讀並勾選目前同意後上傳。JPEG、PNG、HEIC／HEIF，最多 10 MiB、照片長邊 1200～6000 像素，照片庫最多三張，沿用網站的本人擁有權、稽核與人物姿勢檢查；HEIC 可能無法本機預覽。官網入口作為不支援選檔／上傳時的備援。對話附圖不會自動下載，也不當作照片同意。
- 新增三個 app-only 工具：`get_photo_upload_consent`、`create_photo_upload`、`complete_photo_upload`。上傳權限只有 5 分鐘，放在 `_meta.upload`，不進 AI 上下文；不需要將會員 token 交給 iframe。檔案以 signed multipart POST 直傳私人 S3；opaque response 不代表成功，須後端完成物件、格式、大小與人物檢查才加入照片庫。上傳或重試不呼叫 AI、不扣生成額度。
- `prepare_try_on`：建立 10 分鐘有效的確認內容，綁定本人、人物來源與服裝素材版本，尚不扣額度或呼叫模型。
- `confirm_try_on`：使用者明確確認後才傳 reviewId／confirmed=true。後端固定使用 MCP 通道；同一 review 重送只回原任務。確認跨日本午夜失效，需重看新日額度。
- `get_try_on_job`／`get_try_on_jobs`：唯讀查進度、更新短效圖片網址或恢復任務。UI 關閉不取消後端任務。沿用 conversationId 可比較本次最近 12 筆任務；省略可查本人最近 MCP 任務。
- 每會員 MCP 每日 3 次，網站每日 5 次，依日本午夜分開計算。相同有效素材結果只在同通道內重用，不重扣額度。失敗不自動重送；新確認可能另扣一次額度。
- MCP 圖片於**完成當日**日本午夜到期；跨午夜任務的額度計入送出當日，圖片保存到完成當日午夜。私人網址最多 120 秒且不超過圖片到期，已載入的生成圖不因網址到期消失；重繪沿用相同網址已成功載入的圖片。載入失敗時按「恢復任務／更新本次圖片」以唯讀查詢更新網址，不重新生成或扣額度。圖片本身到期時 UI 才隱藏結果。worker 在輪詢時清理 S3 物件，失敗保留清理旗標重試，不代表物件能在到期瞬間完成實體刪除。
- 私人照片、模特兒預覽與生成圖片的網址放在 tool result `_meta.media`，不放進 structuredContent 或 AI 上下文。試穿 UI 的 resourceDomains 與 connectDomains 僅加入後端宣告的精確私人 S3 origins；前者供圖片，後者供直接上傳，不允許 iframe 直接 API fetch 或取得會員 token。方案介面仍不需外部網路連線。
- MCP 生成圖不出現在網站預設生成圖列表，也不可作為網站收藏的生成圖；搭配本身仍可繼續使用。未提供 MCP 場景變換工具。

執行 `backend/.venv/Scripts/python.exe backend/manage.py migrate`（或於 backend 目錄執行 manage.py），並重新啟動既有 `manage.py try-on-worker`，才能使用新的確認紀錄與 MCP 到期規則。先確認沒有任務處理中再重啟 worker。MCP 仍使用本機 3001，不需外部 HTTPS MCP。

## 會員連線與網站管理

1. 在 backend 執行 `.venv/Scripts/python.exe manage.py migrate`，套用 `018_mcp_tokens.sql`。
2. backend 的 `MCP_ENDPOINT` 預設為 `http://127.0.0.1:3001/mcp`，供 `/account/mcp` 顯示及複製。
3. 以已驗證 Email 的會員登入 `/account/mcp`，建立 token；只在建立／重建回傳一次，後端僅存 SHA-256 雜湊。90 天到期，一人一個有效值。重建／撤銷立即失效，請勿貼入 AI 對話。
4. 在 AI 客戶端設定 HTTP `Authorization: Bearer <本人 token>`，再呼叫 `get_member_status` 驗證。公開目錄與選款可以免 token。
5. MCP 每個帶憑證的 HTTP 請求都向 FastAPI 驗證，無會員快取；不信任對話中的會員 ID 或通道。私人操作仍需各自的照片同意／生成確認。

`MCP_DEV_TOKEN` 是既有開發 gate，不能與會員 token 混用；測試會員流程時請不要設定它。stdio 目前只支援公開功能。`/api/health` 的 mcp capability 現在啟用的是網站 token 管理，不代表試穿／草稿已開放。

## 啟動

需要 Node.js 22 以上，以及現有 FastAPI。PowerShell：

```powershell
# 終端機一：從專案根目錄啟動現有 API
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
# 終端機二：從專案根目錄啟動 MCP
cd mcp-server
npm ci
Copy-Item .env.example .env
npm run build
npm start
```

已存在 .env 時直接使用，不要重複覆蓋。預設端點為 `http://127.0.0.1:3001/mcp`。

### 官網入口設定

在 **mcp-server/.env** 明確設定官網 origin，作為「到官網新增本人照片」的連結：

```dotenv
KINUTABI_API_BASE_URL=http://127.0.0.1:8000
KINUTABI_WEB_BASE_URL=http://localhost:5173
```

`KINUTABI_WEB_BASE_URL` 使用瀏覽器實際登入的網址（localhost 與 127.0.0.1 視為不同 origin），不加 `/try-on` 或其他路徑。未設定時預設為 `http://127.0.0.1:8000`，適用 FastAPI 提供 frontend/dist 的模式；Vite 開發模式需明確指定 5173。部署後填官網 HTTPS origin。API、官網、商品圖片 CDN 與 MCP_PUBLIC_ORIGIN 各自用途不同，不會自動互相替代。

MCP 會組成完整的 `/try-on?plan=...` 網址；backend 的 PUBLIC_ORIGIN 仍供後端原有用途，不能取代這項 MCP 官網設定。設定或修改後重啟 MCP，重新載入工具並開啟新的試穿卡片。UI 先檢查 host 的 openLinks 能力，開啟請求最多等待 8 秒；分別顯示未支援、拒絕、逾時或已接受的狀態。「已接受」不代表網頁已顯示。備援提示在點擊後即顯示，不能當作拒絕證據；使用者可按「請 AI 在 Codex 開啟官網」送出明確訊息，由 AI 使用瀏覽器面板工具開啟，不自動登入、上傳或生成，亦可複製官網網址。更新後的 HTML 由 MCP Server 提供，plugin ZIP 不含 UI，這次不需重新安裝外掛。

商品圖片若為 `/assets/...`，在後端提供 frontend/dist 的模式下可沿用 API origin。若使用 Vite 開發站，將 `KINUTABI_ASSET_BASE_URL` 設成 `http://127.0.0.1:5173`，並啟動該前端。CloudFront 圖片需將精確 HTTPS origin 加入 `KINUTABI_IMAGE_ORIGINS`。這些設定同時用於圖片 URL 驗證與資源 CSP，不允許任意圖片網域。

目前後端的方案封面已使用專案 CloudFront 圖片。MCP 仍在本機 `http://127.0.0.1:3001/mcp`；本機 .env 應設定 `KINUTABI_IMAGE_ORIGINS=https://dkwx35rlj68fs.cloudfront.net`，且不設定 MCP_PUBLIC_ORIGIN。圖片 CDN 與 MCP Server 是兩個不同來源。若未設定圖片白名單，MCP 會把該圖片 URL 省略為 null，卡片便只有文字。

修正圖片來源後需重啟本機 MCP 並重新載入客戶端的工具／UI 資源。v2 URI 用於避免舊卡片 CSP 快取；新對話呼叫 show_plan_picker 後確認圖像載入。驗證腳本也會檢查真實方案圖片 URL 非空，且其 origin 已宣告在 UI CSP。

stdio 模式：`npm run stdio`，或客戶端直接執行 `node --env-file-if-exists=.env main.mjs --stdio`，working directory 設為本資料夾。stdout 保留給協定，啟動訊息僅送 stderr。

## 本機互動預覽

停止占用 3001 的 `npm start` 後，改執行：

```powershell
npm run preview
```

開啟 `http://127.0.0.1:3001/_dev`。此模式同時提供 `/mcp`，以官方 AppBridge 將 SDK client 與 `sandbox="allow-scripts"` iframe 連接。畫面下方顯示工具互動、AI 上下文及明確訊息的接收結果，**沒有 AI 模型，也不是 Codex／ChatGPT 實際驗收**。

預覽 host 僅允許 loopback，不能搭配 developer token 或 MCP_PUBLIC_ORIGIN；需要本機預覽時先停用這兩項設定。正式 `npm start` 不提供 `/_dev` 路由。UI 不依賴 iframe 的表單提交或直接 fetch FastAPI，查詢走 bridge；使用者內容以 textContent 呈現。

## 客戶端連接

### Codex 本機直接連線

對正在同一台電腦執行的 Server，先在 PowerShell 執行：

```powershell
codex mcp add kinutabi --url http://127.0.0.1:3001/mcp
codex mcp get kinutabi
```

此命令會新增本機 Codex 的 MCP 設定。之後重新載入客戶端或開新對話，再確認工具是否載入。手動 TOML 等價設定如下，不需同時用兩種方式重複新增：

```toml
[mcp_servers.kinutabi]
url = "http://127.0.0.1:3001/mcp"
```

此本機目錄原型未設定 MCP_DEV_TOKEN 時，不需身分驗證。不需為了此連線執行 OAuth login。直接設定 MCP 工具不保證客戶端支援 MCP Apps UI，需分別驗收。

### 「新增自訂 MCP 伺服器 → 建立為外掛程式」

這是遠端外掛建立流程，與本機 Codex 直接連線不同。依官方 quickstart，此入口填入可從外部存取的 HTTPS `/mcp` 網址；不要填開發機的 `http://127.0.0.1:3001/mcp`。若遇到「應用程式的部分設定遭到拒絕」，先檢查是否誤把 localhost 交給此遠端入口，而不是先更改工具或認證。

若要走此入口，需另建可存取的 HTTPS 部署或開發 tunnel，再選擇相符的認證方式。若上游回應 `403 Invalid Host: ...`，在 mcp-server/.env 加入該 tunnel 的精確 origin，例如：

```dotenv
HOST=127.0.0.1
MCP_PUBLIC_ORIGIN=https://your-tunnel.trycloudflare.com
```

此設定不含 `/mcp`，不接受萬用字元。重啟 `npm start` 後只允許該公開 hostname 與原有 localhost，不關閉 Host／Origin 防護。外掛表單的伺服器網址仍須填 `https://your-tunnel.trycloudflare.com/mcp`。Quick Tunnel 重建後網址可能改變，需同步更新 .env、重啟服務及更新外掛連線。

本里程碑僅有公開目錄查詢；未設定 MCP_DEV_TOKEN 時可選「無需身分驗證」。若設定了 developer token，就必須使用能傳入對應 Bearer header 的客戶端。正式會員工具另外實作可信會員授權。使用 tunnel 時執行 `npm start`，不公開本機預覽 host。

測試提示：「我們兩位成人想在京都體驗和服，請用 KINU TABI 查詢方案並開啟選擇介面。」

分別確認：工具能被發現及呼叫、MCP Apps 資源是否被客戶端實際渲染、點選是否成功、下一次 AI 回答是否得知選擇。不支援 UI 時使用文字結果；依產品定案改在已驗證支援的客戶端驗收 UI。一般網頁、靜態 HTML 截圖或本機 host 不能當成原生對話內驗收。

ChatGPT 類雲端客戶端無法直接存取開發機 localhost；需要可供該客戶端存取的 HTTPS 端點。MCP_PUBLIC_ORIGIN 只允許入口 hostname，不代理商品圖片；UI 若要在遠端載入圖片，仍需可供使用者存取的圖片 HTTPS origin 與 CSP。正式會員版須完成真正的會員授權。

## 驗證

```powershell
npm test
# 只讀取現有本機 FastAPI，不建立草稿、不使用付費 AI
npm run verify:live
```

`npm test` 先打包 UI，再執行 Node 內建測試。測試使用暫時的本機模擬 API，覆蓋 MCP 工具與資源、HTTP transport、參數與上游資料驗證、錯誤遮罩、圖片網域、瀏覽器 Origin 限制及 developer gate。沙箱環境若拒絕 localhost，需在允許本機連線的環境執行，不能把網路拒絕當測試成功。

驗證紀錄見 [VERIFICATION.md](VERIFICATION.md)。

## 開發邊界

預設僅綁定 127.0.0.1，localhost Host／Origin 檢查使用官方 Express adapter。非 loopback 啟動須設定至少 32 字元的 `MCP_DEV_TOKEN`，請求以 Authorization Bearer 傳入；token 不注入 HTML、不轉交 FastAPI，也不是會員 token。此設定只是原型對外驗證的門檻，不代表已具備 OAuth 或 Cloud Run 正式部署設定。

FastAPI 連線僅使用管理者設定的 origin，禁止工具指定 API URL、會員或服務通道；不跟隨 API redirect。公開圖片 origin 由管理者設定，跨來源 redirect 仍可能被 host CSP 拒絕。上游逾時與錯誤回傳安全訊息，不回原始錯誤細節。

## 官方參考

- [MCP Apps Quickstart](https://apps.extensions.modelcontextprotocol.io/api/documents/quickstart.html)
- [OpenAI：Add UI to your MCP server](https://developers.openai.com/plugins/build/chatgpt-ui)
- [OpenAI：MCP 本機設定](https://learn.chatgpt.com/docs/extend/mcp)
- [OpenAI：遠端外掛與 HTTPS 連接](https://developers.openai.com/plugins/build/app-quickstart)
