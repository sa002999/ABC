# KINU TABI Plugin（本機版 0.1.2）

Agent Plugins 1.0 通用套件，包含 HTTP MCP 連線及繁體中文操作 skill。提供公開方案、逐人搭配、會員連線與 AI 試穿工具；需要客戶端支援 Streamable HTTP。圖形介面另需 MCP Apps 支援。

## 啟動服務

本套件連線 `http://127.0.0.1:3001/mcp`，不包含或自動啟動服務。使用 repo 的 `backend/` 與 `mcp-server/`，詳細設定見 repo 的 `mcp-server/README.md`。

在專案根目錄開啟兩個 PowerShell 終端機：

```powershell
# 終端機一：已安裝依賴、設定資料庫並套用 migration 的 FastAPI
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
# 終端機二：Node.js 22 以上
cd mcp-server
npm ci
# 首次使用才複製；已有 .env 時保留原設定
if (!(Test-Path .env)) { Copy-Item .env.example .env }
npm run build
npm start
```

會員測試不要設定 `MCP_DEV_TOKEN`，它是開發 gate，無法取代會員 token。網站照片上傳需要正常運行的前端；這次驗收停在生成前，不需啟動付費生成。

## 安裝與本人會員憑證

1. 透過客戶端的 Agent Plugins 安裝方式載入此目錄或 ZIP。格式本身不定義統一安裝命令。
2. 在自己的網站 `/account/mcp` 登入已驗證 Email 的會員，建立或沿用本人 token。只在客戶端安全憑證設定輸入，HTTP 請求需送出 `Authorization: Bearer <本人 token>`。
3. token 不得加入本套件、Git、對話或工具參數。套件沒有 token，也不會從既有 MCP 設定自動搬移憑證。通用格式不定義憑證引用欄位；安全儲存與 Bearer 設定由客戶端提供。客戶端若沒有安全憑證設定入口，該客戶端的 plugin 會員功能即尚不可用。
4. 重載客戶端／工具後，呼叫 `get_member_status`。成功才算會員連線通過；匿名公開工具正常不代表會員已授權。

### Codex 本機驗收

套件外的 `plugins/.agents/plugins/marketplace.json` 是本機 Codex 測試用目錄，沒有包進 ZIP。從專案根目錄執行：

```powershell
codex plugin marketplace add ./plugins
codex plugin add kinu-tabi@kinu-tabi-local
```

依 Codex 連線提示設定本人 Bearer token。若該版本沒有提供安全憑證入口，保留既有已認證的直接 MCP 連線供驗收，將 plugin 會員接線列為待驗證；不要假設 `kinutabi` 直接連線的 token 會自動套用到 plugin。

重新載入後選用 KINU TABI plugin。若同時保留直接 MCP 連線，驗收時核對工具來源，避免把直接連線成功記為 plugin 成功。測試提示：

> 請用 KINU TABI 驗證本人會員連線，查詢京都兩位成人的方案並開啟選款介面。選定一位旅客款式後，讓我選模特兒並準備生成確認；停在確認畫面，不要呼叫 confirm_try_on。

## 驗收標準

- 套件：manifest、MCP 設定及 skill 可讀取，ZIP 不含憑證、依賴或服務程式。
- 連線：14 個對話工具及 3 個 app-only 照片工具；公開查詢成功，匿名會員操作遭拒，設定本人憑證後會員驗證成功。
- UI：在原生客戶端顯示方案、選款與人物來源；模特兒／照片由本人選擇後，prepare_try_on 顯示生成前確認及剩餘額度。
- 本次不呼叫 confirm_try_on，不扣試穿額度。程式測試、SDK 資源讀取或本機 sandbox 預覽不能代替原生 UI 驗收。

0.1.1 操作指引加入客戶端新增本人照片：在試穿介面本機選檔、閱讀並同意後上傳，後端檢查通過才加入照片庫。上傳不生成、不扣額度，不支援時使用官網備援。UI 仍由 MCP Server 提供；更新此套件是為同步 skill，避免舊指引只要求到官網。

實測狀態見 repo 的 `plugins/VERIFICATION.md`。

## 重新打包與未來部署

0.1.2 操作指引加入全員日期／時段：先檢查共同門市，再用 `check_party_availability` 或 `show_party_availability` 查詢。以日本時間顯示全員名額、和服租借與整備期間的可用性；選時段只記錄偏好，不保留庫存、不建立預約。

在專案根目錄執行 `./plugins/package.ps1`，產生 `plugins/kinu-tabi-0.1.2.zip`。每次修改套件後重新打包。

未來 MCP 部署到 Cloud Run 後，將 `mcp.json` 的 URL 改為真實 HTTPS `/mcp`，更新版號並重新打包；FastAPI 的 EC2 origin、MCP Host 防護、圖片 CSP 及會員認證部署設定另依服務設定驗證。本機版無法讓雲端 agent 存取使用者電腦的 localhost。

格式參考：[Agent Plugins](https://agent-plugins.org/plugin-authors/mcp-servers)、[OpenAI plugin packaging](https://developers.openai.com/plugins/build/plugins)。
