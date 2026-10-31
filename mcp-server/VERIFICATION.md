# 里程碑一驗證紀錄

日期：2026-10-23。範圍為公開方案探索原型，尚未完成原生客戶端對話驗收。

| 項目 | 結果與證據 |
|---|---|
| 依賴與打包 | npm 安裝完成，lockfile 鎖定版本；HTML 與開發 host 成功打包 |
| 自動測試 | 9 項通過。含真實 SDK client/server 通訊、模擬 API、HTTP、UI 資源、錯誤與輸入防護 |
| 真實 FastAPI | verify:live 查得京都 3 個方案，3 個皆 isDemo。單筆詳情與 picker 工具／資源讀取成功 |
| 真實瀏覽器／本機 host | 官方 AppBridge + sandbox iframe 初始化成功，顯示實際方案與圖片 |
| UI 點選 | 點選情侶方案後，詳情顯示兩人一組 NT$2,800、固定一男一女與測試商品標記 |
| 上下文橋接 | host 收到 planId、城市、總人數、計價單位與尚未預約旗標；此處僅模擬接收，沒有模型 |
| 明確訊息 | 點「請 AI 介紹」後 host 收到使用者訊息；未發送到真實對話 |
| 重新查詢 | sandbox 中查詢按鈕可用；不存在的關鍵字回空結果，摘要 selectedPlan=null |
| 原生 Codex | 待接入實際 MCP 設定並驗證，未宣稱支援完整 MCP Apps |
| 原生 ChatGPT／其他 host | 待接入可存取的端點及驗證 |
| 私人操作／付費 AI | 本里程碑不提供，也未執行 |

修正了 inline script 打包時 replacement 字串中的 `$` 會被解讀的問題，改用 replacer function；sandbox 無 allow-forms 時，查詢使用 type=button 與 bridge，避免依賴表單提交。

FastAPI 商品資料與價格是目前開發示範資料，讀取成功不代表正式商品建檔或交易驗收。

## 2026-10-24 Cloudflare Tunnel 修正

- 對使用者提供的公開 `/mcp` 發送 initialize，實際回應 403，JSON 錯誤為 `Invalid Host: calcium-dealt-baker-development.trycloudflare.com`。此錯誤來自 HTTP Host 白名單，非 token 認證。
- 新增 MCP_PUBLIC_ORIGIN 精確 HTTPS origin 設定，保留 localhost 與 Origin 防護，不允許萬用網域。
- 自動測試增加：未允許的 tunnel Host 回 403、指定 Host 初始化成功、其他 tunnel Host／惡意 Origin 回 403、localhost 仍可用。合計 10 項通過。
- 本機 preview 明確拒絕公開 origin 設定；公開入口僅啟動 main 服務。
- 套用使用者目前的精確 Cloudflare origin 並重啟 main 後，以 SDK 經公開 HTTPS 端點完成 initialize、tools/list 與 list_plans；三個工具可列出，京都回傳 3 個示範方案，isError=false。本機已載入的 kinutabi 工具也再次查詢成功。外掛表單建立與原生 UI 渲染仍待實測。

## 2026-10-24 本機方案卡片圖片修正

- 依使用者最新要求，MCP 僅使用本機 127.0.0.1:3001，已移除本機 .env 的 MCP_PUBLIC_ORIGIN；本次未使用外部 HTTPS MCP 進行驗證。
- 直接查本機 FastAPI 的真實資料，確認方案封面已改用專案 CloudFront 網域 dkwx35rlj68fs.cloudfront.net。原本 MCP 圖片白名單只有 8000，因此三個 imageUrl 都被省略為 null。
- 將專案既有圖片 CDN 加入精確圖片來源白名單與 UI CSP，保留未知來源拒絕行為。沒有新增圖片 proxy 或內嵌大圖傳輸。
- 新 UI 資源 URI 為 plan-picker-v2.html，保留舊 URI 相容讀取，以降低快取舊 CSP 的影響。
- 11 項自動測試通過，新增真實圖片 CDN 類型的回歸案例：未設定時為 null、設定後 URL 保留且 CSP 包含同一 origin。真實目錄驗證新增圖片 URL 非空與 CSP origin 一致性檢查。

Final local verification: SDK client connected directly to http://127.0.0.1:3001/mcp; show_plan_picker returned 3 non-null CloudFront image URLs and v2 resource CSP allowed their exact origin. npm run verify:live passed. Local sandbox iframe visibly rendered all 3 plan photos; screenshot: ../.cache/mcp-verification/local-cdn-images.png. Native ChatGPT/Codex rendering still requires client refresh and a new picker invocation.

## 第二階段：逐人搭配及會員 token（2026-10-24）

- 已套用 `018_mcp_tokens.sql`。token 只在建立／重建回傳一次，儲存 SHA-256 雜湊；會員 row lock 序列化建立、重建及撤銷。
- `npm test`（mcp-server）：12/12。包含新工具、同一 HTTP MCP 服務的匿名／會員憑證隔離、撤銷後下一請求遭拒及禁止 token/userId 工具輸入。
- `RUN_DATABASE_TESTS=1 python -m unittest discover -s tests -p test_mcp.py -v`：3/3。驗證建立、重建、撤銷、到期、Email 驗證、不同會員隔離、真實套餐價格、共同門市、無共同門市保留選擇與無效款式。測試交易已回滾。
- 既有 `test_experience_plans.py` 資料庫套餐回歸：1/1。
- frontend：35/35 測試；TypeScript 與 Vite production build 通過。
- 實際 SDK 直接連線 `http://127.0.0.1:3001/mcp`：7 個工具；京都一男一女情侶方案估計 NT$2,800、共同門市 1 間；匿名會員工具回傳 MCP_TOKEN_REQUIRED。
- 本機 MCP Apps sandbox 已操作兩位旅客不同類別選款、完成摘要並顯示正確金額、共同門市及模擬 AI 上下文；修改旅客 1 的款式後，舊金額與門市摘要消失、旅客 2 的選擇保留，UI 與上下文皆標示須重新檢查。畫面：`.cache/mcp-verification/stage-two-summary.png`（專案根目錄相對路徑）。
- `/account/mcp` 已在 Vite 瀏覽器確認端點顯示、免登入可查看端點、未登入 token 按鈕停用。畫面：`.cache/mcp-verification/stage-two-account.png`。
- 尚待本人實際帳號登入後的頁面點選驗收，以及原生 ChatGPT／Codex 客戶端重新載入 v3 卡片驗收。API 測試使用受控 identity override；未操作本人真實 token，未將測試 token 寫入日誌或提交檔案。
- MCP 仍使用本機 3001；3002 只作本機 sandbox。沒有連線外部 HTTPS MCP、沒有生成圖片、建立預約或占用庫存。

## 第三階段：AI Try-on（2026-10-24）

- 已套用 `019_mcp_try_on.sql`，並在確認沒有進行中任務後重啟既有 worker，載入 MCP 完成當日日本午夜到期規則。MCP HTTP 仍為 `http://127.0.0.1:3001/mcp`。
- 新增 `show_try_on`、`prepare_try_on`、`confirm_try_on`、`get_try_on_job`、`get_try_on_jobs`。總計 12 個工具；方案選擇資源更新為 v4，試穿資源為 `ui://kinu-tabi/try-on-v1.html`。
- MCP `npm test`：13/13，包括確認前零生成、mutation 註記、拒絕偽造身分／通道／未確認參數、私人圖片只置於 `_meta.media`、精確 CSP 圖片來源。
- `RUN_DATABASE_TESTS=1 python -m unittest discover -s tests -p test_mcp_try_on.py -v`：5/5。涵蓋未登入與 no-store、確認／重試／每日 3 次、網站額度不變、確認過期／跨午夜失效、素材變更、本人照片同意撤回、他人來源拒絕、會員隔離、歷程恢復、結果重用、worker 到期及清理。全部交易回滾，模型與私人儲存 mock。
- 既有 `test_generations.py`：12 通過、2 opt-in 真實 AI／儲存測試略過；網站額度、重用、來源同意及 worker 7 天期限回歸通過。
- frontend TypeScript 與 Vite production build 通過。會員頁文案更新為 MCP 試穿已開放。
- 實際 SDK 直接連線本機 3001：12 個工具、新試穿 HTML、包含私人 S3 的精確 resourceDomains、connectDomains 空陣列，匿名試穿遭拒。
- 既有 kinutabi 連線的 `get_member_status` 實際回傳 authenticated=true，沒有讀取或顯示會員 token。
- 模擬 UI fixture 使用本機 3003 與合成測試憑證，只有模型預覽素材，沒有真實 AI 呼叫或資料庫寫入；確認前未勾選會阻擋，確認後顯示模擬任務與結果。此驗證不代表原生 Codex／ChatGPT UI 或真實模型已驗收。
- 最後版本亦確認生成回應後 UI 立即將剩餘額度由 3/3 更新為 2/3（模擬數據）。畫面存於專案根目錄 `.cache/mcp-verification/stage-three-mock-ui.png`，圖片為測試素材，不是 AI 生成圖。驗證後停止 3003 模擬服務。
- 尚待本人重新載入 MCP 工具清單後，在原生客戶端驗收人物來源、官網上傳返回刷新、明確確認後的一次真實模型生成與結果顯示。本次開發沒有扣用本人生成額度或發出付費 AI 請求。

## 2026-10-25 原生試穿回報及網址／顯示修正

- 使用者回報外掛已驗證至 AI 試穿生成後，並指出 Invalid URL、官網按鈕無效及 120 秒後圖片消失。此為使用者實測回報，與前述歷史驗證紀錄分開記錄。
- 根因：UI 對相對 uploadPageUrl 直接呼叫 new URL；顯示計時器將短效網址 TTL 當成圖片到期時間。
- 新增 MCP 的 KINUTABI_WEB_BASE_URL，已在本機 mcp-server/.env 設成使用者指定的 http://localhost:5173；MCP 從受控 origin 及驗證後 planId 組成完整官網連結，忽略不可靠的上游 uploadPageUrl。入口錯誤與 host 開啟失敗有可理解訊息及可複製網址。
- 已載入的生成圖不因 120 秒網址到期被移除；相同圖片在重繪時保留。圖片於完成當日日本午夜真正到期時，才隱藏結果。載入失敗使用「恢復任務／更新本次圖片」做唯讀查詢，不自動生成或扣額度。
- npm test：17/17 通過。新增真實 UI 程式的 DOM／SDK stub 與虛擬時鐘測試，驗證開連結、host 拒絕的 fallback、121 秒後圖片仍存在、重繪保留、真正到期隱藏及失敗後唯讀換網址；SDK 測試包含上游相對／空白／外站入口被受控設定取代。
- 重啟已確認的 3001 MCP 程序，未重啟 FastAPI 或 worker。唯讀 SDK 驗證新工具公告 ui://kinu-tabi/try-on-v2.html，v1 仍可讀取相同新版內容；官網 /try-on?plan=... 回 200。
- 實際已安裝外掛的 show_try_on 成功，uploadPageUrl 回傳 http://localhost:5173/try-on?plan=...，未讀取或顯示會員憑證／私人圖片網址。
- 同步 MCP_SPEC.md、06-api-routes.md、08-page-features-wireframes.md 及 MCP README，明確區分私人網址 TTL 與圖片保存期限；120 秒政策已依本次使用者確認記錄，不再標為待定。
- 尚需使用者重新開啟試穿卡片，確認原生 host 按鈕可實際打開官網。上述虛擬時鐘測試不冒充原生客戶端長時間顯示驗收。本次修正未呼叫 confirm_try_on，未產生新任務或消耗生成額度。

### 官網未開啟的後續回報

- 使用者再次回報未開啟官網，貼出的「若官網未自動開啟，請複製此網址」是 UI 在 openLink 前就顯示的通用備援提示，不能據此認定 host 拒絕或不支援。先前測試只驗證 UI 有送出請求，未驗證原生 host 實際開啟頁面。
- UI 新增 openLinks 能力檢查、8 秒請求逾時及拒絕／接受狀態；非敏感 websiteOpen 狀態同步至 AI 上下文，避免把 host 接受請求當成頁面已顯示。
- 增加使用者主動點擊的「請 AI 在 Codex 開啟官網」，透過 sendMessage 請 AI 開啟官網瀏覽器面板；只開網頁，不自動上傳、登入或生成。保留可複製連結，不使用 window.open 繞過 sandbox。
- npm test：19/19 通過，新增未支援 host、明確點擊才送訊息、接受狀態及逾時的測試。新 UI 公告 v3，保留 v1／v2 相容資源。原生 openLink 無效的具體原因仍需以新版卡片回報的 websiteOpen 狀態判讀，尚不宣稱是網域政策、瀏覽器設定或 host bug。

## 2026-10-25 客戶端新增本人照片

- 新增 app-only 工具 get_photo_upload_consent、create_photo_upload、complete_photo_upload。SDK 可列出共 15 個工具，其中 3 個只供 App；原本對話功能保持 12 個。本人身分由每次 HTTP Bearer 請求驗證，輸入拒絕 token、userId 與任意通道。
- FastAPI 重用既有照片同意、session、三張上限（含未到期上傳預留）、S3 私人儲存、10 MiB／格式／長邊限制、單人人物與身體範圍檢查、擁有權及清理。沒有新 migration，沒有改動 S3 bucket CORS 或公開權限。
- 介面本機選檔／JPEG、PNG 預覽／明確同意後，取得 5 分鐘 signed POST，僅透過精確私人 S3 origin 上傳；會員 token 不進 iframe。表單權限位於 _meta.upload，不進 structuredContent 或 AI 上下文，原始檔名不送往工具或儲存。opaque response 不能作為成功證據，必須後端完整檢查後才加入共用照片庫。
- 傳輸失敗沿用原票證；驗證暫時失敗以原 sessionId／photoId 重試，不再次傳輸、不占另一張預留、不生成或扣額度。介面分別顯示「重試本次上傳」及「重試照片檢查」。關閉介面會失去本機待上傳內容，未完成上傳沿用既有到期清理；準備票證本身逾時而未收到結果時，服務端預留可能持續至 5 分鐘到期，不自動反覆建立票證。
- npm test：25/25 通過。包括同意前不傳檔、過大／格式錯誤不傳檔、signed grant 隔離、拒絕外站上傳、失敗與驗證重試、拒絕照片不加入照片庫、無生成呼叫及既有試穿／目錄／安全回歸。
- RUN_DATABASE_TESTS=1 的 test_mcp_try_on.py：7/7 通過。新增路由會員拒絕與 no-store、同意版本／嚴格布林、擁有權隔離、三張上限、缺少物件、無效／到期照片與重複完成驗證。資料庫全數回滾，照片為合成圖片、私人儲存與模型生成皆 mock。
- 另執行既有網站 API 上傳備援與姿勢服務失敗後可重試的 2 項回歸，2/2 通過，資料庫回滾。
- 人物姿勢檢查 4/4 通過，包含實際本機 MediaPipe 模型拒絕合成空白圖片並接受專案既有模特兒參考圖；未呼叫雲端辨識或付費生成。
- 原沙箱 TestClient 停住，於沙箱外完成測試並停止原卡住的測試程序。本機 FastAPI 當時未在 8000 監聽，已啟動既有 uvicorn；MCP 已重啟，不啟動／重啟生成 worker。
- 實際唯讀 HTTP／SDK 檢查：3 個新後端路由已提供，匿名照片同意回 401/no-store；MCP 公告 v4 UI，提供本機選檔及同意介面，私人 connectDomains 為 2 個精確 HTTPS S3 origins；既有原生外掛 get_member_status 仍 authenticated=true。
- 原生 Codex 選檔對話框、真實 signed POST 上傳與客戶端 CSP 相容性尚需本人選擇照片驗收；未以 mock 或資源讀取冒充原生上傳成功。本次沒有上傳本人真實照片、沒有付費 AI 呼叫。
- repo plugin 操作 skill 同步更新並產出 0.1.1 ZIP，不修改或複製已安裝外掛的憑證，不自動發布帳號版更新。

## 2026-10-25 全員日期／時段

- 新增公開唯讀 check_party_availability、show_party_availability；共 14 個對話工具與 3 個 app-only 照片工具。picker 資源更新 v5，保留舊 URI；試穿仍為 v4。
- FastAPI 公開 POST /api/catalog/party-availability 嚴格接受全員真實搭配、城市、共同門市與最多31天日本日期。沿用套餐、款式／性別、24小時～90天、關店、接待名額、不同實體和服及整備重疊規則；回應 no-store，不建立草稿、報價或暫留。
- 初次實際31天查詢發現逐場次資料庫往返會逾時，改為一次查詢場次名額及一次批次查詢庫存候選。庫存衝突 SQL 由查詢與正式暫留共用，未新增快取或新資料表。
- UI 在搭配摘要後提供共同門市與日期起訖；直接 show_party_availability 可恢復指定搭配與日期的最新查詢。不可用時段不可選，沒有可用時段時保留搭配。修改搭配、門市或日期清除舊結果及選時段偏好；選擇只同步探索偏好，未保留庫存。
- npm test：28/28 通過，涵蓋完整 party 轉送、錯誤與嚴格輸入、拒絕上游虛稱保留、恢復日期介面、只選可用時段、修改條件後結果失效、無可用時保留搭配，以及既有照片／試穿回歸。
- test_party_availability.py：4/4 資料庫回滾測試通過。涵蓋同款不同實體、全員名額、混合方案、套餐不完整、異城市／門市、日期邊界、整備衝突、收件時間與關閉場次，以及查詢不新增預約資料。
- 另4項既有預約回歸通過：時間邊界／私人路由、報價與暫留原子性／重送／資料庫重疊約束、整備期間、兩會員同時競爭同一實體庫存。並行測試初次在建立草稿時422，查明原測試未建立目前必要的 plan_kimonos 關聯；補齊測試資料及清理後重跑通過，兩人競爭結果為一筆201、一筆409。合計8項後端測試通過，沒有付費服務呼叫。
- 實際本機 HTTP MCP：node verify-availability.mjs 通過。匿名三位成人、31天、62個示範場次，62個全員可用；查詢約6.7秒，v5資源可讀。未呼叫付費生成或建立真實預約。
- 本機 FastAPI 已由原 reload 程序載入新路由，MCP 已重新啟動。Codex 本對話的工具清單仍未刷新到新增工具；原生日期選擇及時段點選需重新載入外掛工具後驗收，不以 SDK／模擬 UI 測試宣稱完成原生驗收。
- repo plugin skill、文件及 ZIP 更新為0.1.2；兩份官方 JSON schema 驗證通過，ZIP 四個檔案與來源完全相符且不含會員 token。未修改已安裝外掛的憑證或發布帳號版更新。
