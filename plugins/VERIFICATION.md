# Plugin 驗證紀錄

日期：2026-10-25（Asia/Taipei）。版本：kinu-tabi 0.1.0，本機 HTTP 版。

## 已完成

- `plugin.json`、`mcp.json` 使用 `Test-Json -SchemaFile` 通過從 agent-plugins.org 下載的 1.0.0 官方 JSON schema。
- 通用 MCP schema 為封閉格式，不接受 server 的 `extensions` 欄位；因此未將 OpenAI 文件中的 auth 擴充放進通用 mcp.json。會員 Bearer 憑證由客戶端另行設定，套件不宣稱通用自動登入。
- ZIP 僅包含 plugin.json、mcp.json、README.md、skills/kinu-tabi/SKILL.md 四個檔案；採明確檔案清單，排除 .env、token、node_modules、後端與開發資料。已重新打包並檢查 ZIP 項目與來源內容。
- `mcp-server/npm test`：13/13 通過，包含會員憑證隔離／撤銷、試穿前確認、私人媒體隔離、CSP 與 HTTP 防護。首次 esbuild 遭沙箱 EPERM，取得權限後重跑通過。
- `npm run verify:live`：真實本機 FastAPI 京都 3 筆示範方案、詳情、圖片來源與 picker 資源讀取通過。
- 以官方 SDK 讀取套件 mcp.json 的實際 HTTP URL：列出 12 個工具、京都 3 筆公開方案、匿名 get_member_status 回 MCP_TOKEN_REQUIRED、試穿 HTML 資源可讀取。此項不代表原生 UI 或會員成功連線。

## 尚未完成

- Codex plugin 安裝及從 plugin 來源呼叫會員工具。曾以不符合目錄慣例的 marketplace 路徑嘗試註冊，CLI 拒絕；已改為 plugins/.agents/plugins/marketplace.json。其後的使用者設定寫入權限請求遭使用者拒絕，未完成註冊或安裝。
- `codex mcp get kinutabi` 確認有既有直接 HTTP 連線，Authorization 由 CLI 遮罩。未讀取、複製或搬移憑證；既有連線不能當作新 plugin 的會員成功證據。
- 本人會員成功驗證、原生 Codex 方案／人物來源介面、本人選人物後的 prepare_try_on 確認畫面，仍需安裝、設定憑證並重新載入工具後驗收。
- 本次未呼叫 confirm_try_on，沒有付費 AI 生成或試穿額度消耗。

安裝命令與原生驗收提示見 kinu-tabi/README.md。禁止以 SDK 資源讀取或模擬測試替代上述未完成項目。

## 同日後續實測（更新前述歷史狀態）

- 使用者已自行安裝外掛並刪除原本的直接 MCP 連線；後續曾實際得到 MCP_TOKEN_REQUIRED，確認缺少憑證時會員操作確實遭拒。其後 get_member_status 成功回 authenticated=true。
- 使用者回報原生介面已驗證至 AI 試穿生成完成；其回報的官網按鈕及圖片顯示問題已在 MCP Server 修正。這些 UI 由服務端提供，不包含於 plugin ZIP，故本次未修改套件或憑證設定。
- 修正與驗證細節見 ../mcp-server/VERIFICATION.md 的 2026-10-25 紀錄；重新載入工具並開啟新試穿卡片以取得最新 UI（目前 v4）。

## 0.1.1 操作指引更新

- skill 改為引導使用者在 MCP 試穿介面選本機照片、預覽、閱讀並明確同意後上傳；官網作為備援。三個新照片工具只供 App，不讓 AI 接收照片二進位、原始檔名、會員 token 或 signed grant。
- MCP Server 現在提供 v4 UI，12 個對話工具＋3 個 app-only 工具。原生上傳相容性尚待使用者選檔實測，詳見 ../mcp-server/VERIFICATION.md。
- 套件名稱與 HTTP endpoint 保持相同；plugin version 更新為 0.1.1，供使用者更新安裝的 skill。沒有自動更新帳號版 plugin 或修改既有會員憑證。

## 0.1.2 全員日期／時段操作指引

- skill 加入 check_party_availability／show_party_availability，先確認全員搭配與共同門市，再查日本日期；可用結果只代表查詢當下，不保留或建立草稿。
- MCP Server 提供 v5 picker、14個對話工具與3個 app-only 照片工具。28項 MCP／模擬UI測試與4項新後端資料庫測試通過；實際匿名三位成人31天查詢回傳62個示範場次。細節見 ../mcp-server/VERIFICATION.md。
- plugin.json／mcp.json 通過官方 schema，kinu-tabi-0.1.2.zip 四個檔案逐一比對來源一致且不含 token。既有HTTP端點不變，不自動修改會員憑證或發布已安裝帳號版外掛。
- 原生 Codex 日期與時段UI尚待重新載入工具後驗收；現有對話尚未刷新新增工具，不能以 SDK 查詢冒充原生客戶端驗收。
