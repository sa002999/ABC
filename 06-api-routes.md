# KINU TABI｜API Route 開發表

整理日期：2026-10-16。依今日[產品體驗](./01-product-experience.md)、[技術規格](./02-functional-technical-spec.md)、[會員流程](./04-member-flow-decisions.md)及兩張最新圖表整理，格式參照 WeHelp 作業的「HTTP 方法＋路徑＋用途＋Request／Response」。

**狀態：本表是待實作的介面規劃，不是已完成的 API 清單。** 本次檢查此工作區 `kinu-tabi/` 只找到靜態網站原型，未找到 KINU TABI 的 FastAPI 路由實作；不據此推定其他工作區或部署環境的進度。

「既有」代表已寫在現有規格；「補充」代表依今天確認的體驗提出的路由命名與契約建議，尚未實作。新增路由是既定功能的開發拆解，不新增產品功能，也不改寫老師原始要求。

## 1. 怎麼看這張表

```text
GET    /api/plans                 讀取方案列表
GET    /api/plans/{planId}        讀取一個方案
POST   /api/looks                 新增一筆收藏
PATCH  /api/looks/{lookId}        更新一筆收藏
DELETE /api/looks/{lookId}        取消一筆收藏
```

- `{planId}` 是路徑參數，例如 `/api/plans/plan_001`。文件原本的 `:id` 統一寫成 FastAPI 常見的 `{id}` 形式，實際網址不包含大括號。
- `?city=TOKYO&page=0` 是查詢參數；`POST`／`PATCH` 的資料通常放在 JSON Request Body。
- 網站私人 API 使用 `Authorization: Bearer <Firebase ID token>`；後端驗證 token 與本人資料權限。Email 已驗證才可付款及建立 MCP token。
- 下表「會員」都含本人擁有權驗證；「門市」限制所屬門市；「總管」指總管理員；「退款授權」須另驗退款權限。不可只驗有登入。
- 除圖片直傳使用簽名 URL 外，本站 API 使用 HTTPS／JSON／UTF-8。表內欄位及回傳包裝為本次統一建議，實作前應落成 Pydantic／OpenAPI 契約。

## 2. 公開商品、方案、門市

對應開發表 01、04、05。公開瀏覽不要求先登入。

| 方法 | Route | 用途／主要 Request | 主要 Response | 權限 | 來源 |
|---|---|---|---|---|---|
| GET | `/api/health` | 服務健康檢查 | `status`，不含機密 | 公開 | 既有 Week 9 |
| GET | `/api/plans` | 方案篩選；`city, store, audience, style, minPrice, maxPrice, date, keyword, page` | `data[], nextPage`，TWD 價格、包含服務 | 公開 | 既有；補分頁契約 |
| GET | `/api/plans/{planId}` | 單一方案 | 方案內容、價格、適用門市、可選商品及加購 | 公開 | 既有 |
| POST | `/api/plans/compare` | 和服比較；`lookIds` 2～3 筆、對應 `planIds` | 同欄位的圖片、類型、目前方案／配件／總價 | 會員 | 既有；補搭配識別 |
| GET | `/api/stores` | 門市列表；`city` | `data[]`，名稱、地址、營業資訊 | 公開 | 既有 |
| GET | `/api/stores/{storeId}` | 門市詳情 | 地址、交通、營業資訊、時區 | 公開 | 既有 |
| GET | `/api/stores/{storeId}/availability` | 公開名額；`from, to, partySize`，可帶方案／服務條件 | 可選場次、全員可用狀態；不含其他會員資料 | 公開 | 既有 |
| POST | `/api/catalog/party-availability` | `city, storeId, guests[{guestType,planId,kimonoId}], from, to`；1～3 位成人，最多31天日本日期 | 全員接待名額、不同實體和服於租借及整備期間的可用性、各人歸還時間、不可用原因、isDemo；不建立草稿或保留 | 公開 | MCP 全員查詢已實作；沿用預約規則 |
| GET | `/api/kimonos` | 和服列表；門市、方案等篩選 | 商品、款式、目前價、展示圖 | 公開 | 補充 |
| GET | `/api/kimonos/{kimonoId}` | 單一和服與展示圖切換資料 | 商品圖、預製穿搭圖、已知示意配件 ID | 公開 | 補充 |
| GET | `/api/accessories` | 可售配件；和服／門市／類型條件 | 配件 ID、價格、圖片、適用條件 | 公開 | 補充 |
| GET | `/api/models` | 商店 AI 人物來源照 | 可選模特兒 ID、性別 role、預覽；女生與男生各 3 位 | 公開 | 補充 |
| GET | `/api/photography-options` | 同地點、同和服的外拍比較及加值選項；`storeId, kimonoId, date` | 場景、內含服務、TWD 價格、季節日期、場次、輸出選項 | 公開 | 補充 |

比較 API 的原規格只列 `planIds`；今天的比較含每份收藏的配件與圖片，需增加 `lookIds` 或等價搭配識別，並驗證收藏屬於會員。未登入的外拍比較可由 `photography-options` 回傳資料在前端並排，不要求先登入。

列表建議沿用作業風格：`page` 從 0 開始、預設 `pageSize=12`、上限 50、最後一頁 `nextPage=null`；這是建議契約，不是現有實作證據。頁面篩選條件亦應保存在前端 URL。

## 3. 會員與帳號

對應開發表 01。Firebase SDK 負責註冊、登入、Email 驗證及密碼重設，不另建一套帳密資料庫。

| 方法 | Route | 用途／主要 Request | 主要 Response | 權限 | 來源 |
|---|---|---|---|---|---|
| PUT | `/api/account` | 首次登入後冪等同步已驗證的 Firebase 身分，不收帳密 | 本站會員識別與初始化結果 | 會員 | 補充 |
| GET | `/api/account` | 取得 Firebase UID 對應的本站會員資料 | 會員資料、驗證狀態、可用會員入口 | 會員 | 補充 |
| GET | `/api/account/generation-usage` | 查網站與 MCP 生成用量 | 分開的上限／已用／剩餘、`Asia/Tokyo`、重設時間 | 會員 | 既有 |
| POST | `/api/account/deletion-check` | 刪帳前檢查 | `canDelete, blockers[]`、刪除範圍及期限 | 會員 | 既有 |
| DELETE | `/api/account` | 確認永久刪帳；敏感操作重新驗證身分 | `deletionId, status` | 會員 | 既有 |

`PUT /api/account` 只同步已驗證的 Firebase 身分並初始化本站資料，不提供修改角色／Email 驗證狀態的能力，也不觸發生成或付款。刪帳可先回 `202` 表示清除排程中，但必須立即阻止帳號存取並撤銷 token；後端再次檢查未結事項，不能只相信 deletion-check 的舊結果。備份最遲 10 天清除與還原重套刪除紀錄屬後端工作。

和老師作業的差別：舊專案的 `POST /api/user`／`PUT /api/user/auth` 是自行處理帳密；這次採 Firebase，登入後用 Firebase ID token 呼叫本站 API。

## 4. 照片、AI 試穿與場景

對應開發表 02。所有建立任務都須確認生成；本人照另需照片處理同意。網站直接經 FastAPI 呼叫 Vertex，不必繞 MCP。

| 方法 | Route | 用途／主要 Request | 主要 Response | 權限 | 來源 |
|---|---|---|---|---|---|
| POST | `/api/try-on/sessions` | 建立試穿工作階段；人物來源、商品、照片同意版本（本人照時必要） | `sessionId, consentStatus` | 會員 | 既有 |
| GET | `/api/try-on/photos` | 會員人物照片庫，最多 3 張；不列生成圖 | `data[], maxPhotos`；照片 ID、短效預覽、狀態 | 會員 | 補充 |
| DELETE | `/api/try-on/photos/{photoId}` | 刪除指定原圖；不刪生成圖／收藏 | `ok, deletionStatus` | 會員 | 補充 |
| GET | `/api/try-on/sessions` | 內部工作階段資料；人物選擇改用會員照片庫，不在試穿頁提供歷史工作階段選單 | `data[]`，照片 ID、驗證狀態、授權預覽 | 會員 | 補充 |
| POST | `/api/try-on/sessions/{sessionId}/upload-url` | 已同意的本人照上傳；`contentType, size, fileName` | 私有 S3 短效 `uploadUrl`、上傳方法、必要標頭及暫存照片 ID | 會員 | 既有 |
| POST | `/api/try-on/sessions/{sessionId}/validate` | 上傳後驗真實物件與圖片品質；`photoId` | `photoId, status, issues[]` | 會員 | 既有 |
| DELETE | `/api/try-on/sessions/{sessionId}/photo` | 刪除此階段的本人原圖 | `ok`，不刪已保存生成圖／收藏 | 會員 | 既有 |
| POST | `/api/try-on/sessions/{sessionId}/generations` | 確認穿搭生成；`kimonoId, planId, photoId` 或 `modelId, accessoryIds, confirmed` | `jobId, status` | 會員 | 既有 |
| GET | `/api/try-on/jobs/{jobId}` | 查任務進度；查詢不扣次 | 狀態、`generationId`、授權結果網址及期限、失敗原因 | 會員 | 既有 |
| POST | `/api/try-on/jobs/{jobId}/scene-generations` | 既有成功穿搭任務接續場景；`sceneId, confirmed` | 新場景任務 `jobId, status` | 會員 | 既有 |
| POST | `/api/try-on/sessions/{sessionId}/scene-generations` | 預製圖直接合成場景；`prebuiltImageId, kimonoId, modelId, sceneId, accessoryIds, confirmed` | 場景任務 `jobId, status` | 會員 | 補充 |
| GET | `/api/try-on/generations` | 我的網站生成圖；可依狀態／日期分頁 | `data[]`、圖片到期時間及搭配關聯 | 會員 | 補充 |
| DELETE | `/api/try-on/generations/{generationId}` | 提前刪除本人生成圖 | `ok`；收藏保留並改商品圖 | 會員 | 既有 |

照片實際直傳使用 API 回傳的 S3 簽名 URL，不新增 `PUT /api/...` 當作 S3 網址。驗證需檢查伺服器實際收到的大小、格式、方向、EXIF 與照片品質，不能只信前端。重新上傳仍沿用 upload-url→validate 流程，成功替換後刪除舊原圖。

**補充的場景 route 是舊規格的重要缺口：預製穿搭圖沒有 AI jobId。** 因此另提供 session 入口，兩條場景 route 共用一個後端場景業務服務；若日後統一為同一入口，應同步更新本表及原規格，避免做兩套生成邏輯。

網站穿搭／場景共用每日 5 次，圖自完成起保存 7 天；MCP 另計每日 3 次且圖片當天日本午夜刪除。冪等鍵相同的重送不重扣，失敗後會員確認重新建立任務時使用新鍵。供應商內部呼叫次數與會員任務額度分開記錄。

## 5. 收藏與比較

對應開發表 04。「造型收藏」是已選定的五選一追加功能；比較為今日產品流程的既定配套。

| 方法 | Route | 用途／主要 Request | 主要 Response | 權限 | 來源 |
|---|---|---|---|---|---|
| POST | `/api/looks` | 新增收藏；`planId, kimonoId, accessoryIds, sceneId`，網站 `generationId` 選填 | `lookId`、搭配內容、目前 TWD 價格、圖片來源 | 會員 | 既有 |
| GET | `/api/looks` | 我的收藏列表；分頁 | 收藏搭配、有效生成圖或商品圖、目前售價 | 會員 | 既有 |
| PATCH | `/api/looks/{lookId}` | 明確確認更新；搭配欄位與版本 | 新收藏版本、更新後搭配與目前價格 | 會員 | 既有 |
| DELETE | `/api/looks/{lookId}` | 取消收藏 | `ok`，不刪原圖或生成圖 | 會員 | 既有 |

臨時加入／移除示意配件可先在前端改搭配與摘要，不呼叫生成 API；若要保存進既有收藏才 PATCH。圖片本身仍可能含未選配件，須分開保存 `selectedAccessoryIds` 與示意配件資訊。沒有生成圖也能收藏；MCP 當日圖不得當網站收藏的生成圖來源。收藏／比較只讀目前售價，最終付款報價另由後端確認。

## 6. 草稿、報價、付款與會員預約

對應開發表 05。草稿／報價不佔庫存，只有「前往付款」成功建立整筆 hold 才暫留 10 分鐘。

| 方法 | Route | 用途／主要 Request | 主要 Response | 權限 | 來源 |
|---|---|---|---|---|---|
| POST | `/api/booking-drafts` | 建立或恢復本人唯一有效草稿；已有草稿則沿用且不覆蓋內容，修改走 PATCH | 新建 201／恢復 200，`draftId, status`；建立起 7 天到期，正式成立後移出草稿，不保留庫存 | 會員；MCP 限草稿能力 | 既有 |
| GET | `/api/booking-drafts/{draftId}` | 網站讀取本人或 agent 所建草稿 | 草稿內容、版本、有效性及需重新確認欄位 | 會員 | 補充 |
| PATCH | `/api/booking-drafts/{draftId}` | 修改草稿；旅客／搭配／場次／聯絡資料、版本 | 更新草稿與版本 | 會員；MCP 限草稿能力 | 既有 |
| POST | `/api/pricing/quote` | 以 `draftId` 及版本重新計價 | `quoteToken, currency:TWD, lineItems, total, expiresAt` | 會員 | 既有 |
| POST | `/api/availability/holds` | 前往付款；`draftId, quoteToken`，驗 Email 與全員資源 | `holdId, expiresAt, serverTime`，10 分鐘期限 | 已驗證 Email 會員 | 既有 |
| GET | `/api/availability/holds/{holdId}` | 重整或付款返回時查 hold 狀態 | `status, expiresAt, serverTime`，不延長期限 | 會員 | 補充 |
| POST | `/api/bookings` | 提交付款／正式預約流程；`holdId, quoteToken, prime, contact`、取消政策版本／同意 | `orderNo, paymentStatus`；確認成立後才有 `bookingNo` | 已驗證 Email 會員；不開給 MCP | 既有；補付款語意 |
| GET | `/api/orders/{orderNo}` | 付款待確認、離開或返回網站後查狀態 | 付款／預約處理狀態，成立時含 `bookingNo` | 會員 | 補充 |
| POST | `/api/payments/tappay/callback` | 接收所選付款模式適用的供應商後端通知 | 驗證、查核、冪等處理後依供應商契約確認接收 | 供應商通知驗證 | 既有 |
| GET | `/api/bookings` | 我的預約列表；狀態、日期、分頁 | `data[]`，預約／付款／退款摘要 | 會員 | 補充 |
| GET | `/api/bookings/{bookingNo}` | 單筆本人預約 | 旅客、搭配、價格、門市時間、狀態、票券及退款摘要 | 會員 | 既有 |
| GET | `/api/bookings/{bookingNo}/cancellation-quote` | 取消前試算，不執行取消 | TWD 可退金額、政策、計算時間 | 會員 | 補充 |
| POST | `/api/bookings/{bookingNo}/cancel` | 確認取消；`confirmed, reason` | 取消結果及退款申請狀態，不代表已退款 | 會員；不開給 MCP | 既有 |
| GET | `/api/bookings/{bookingNo}/voucher` | 會員動態 QR；伺服器檢查有效預約與本人 | `qrPayload, qrExpiresAt, checkInDeadline, status` | 會員 | 補充 |

本次沿用既有 `POST /api/bookings` 統一處理「提交付款→確認→正式預約」的命名，避免再加一個有相同扣款作用的 `POST /api/orders`。它可以先建交易訂單、回 `202 PAYMENT_PENDING`，但不能提前把正式預約、票券或成功通知標成已成立。若實作選擇拆出付款 route，需明確決定唯一扣款入口並同步契約。

**付款規則：**後端計算 TWD 整數元；付款成功且有效 hold 轉正式保留才成立正式預約。重複請求須冪等。待確認付款不得因倒數結束就釋放；背景查核確認未成功才釋放。已收款但無法成立預約須通知並全額退款，不能自動換商品。TapPay Prime 不作長期保存或記錄到一般日誌。

**取消規則：**依日本場次開始時間，超過 7×24 小時全退，剩餘等於或少於 7×24 小時不退；試算與提交之間可能跨界線，提交須重新計算，若可退金額改變須讓會員重新確認。實際退款由授權後台人員處理。改期取消原單再建新單。

**QR 規則：**每筆一張、每 5 分鐘更新、舊碼失效、不含個資；本人在指定店開始後 30 分鐘含界線前報到，排隊後仍可核銷；已取消／已核銷／逾期未報到不可用。更新 QR 不延長期限。此處的 GET 取得憑證不能自動執行核銷。

## 7. MCP token 與工具

對應開發表 03。網站管理 token 使用 Firebase 身分；外部 agent 使用 MCP token。兩者不可互換。

| 方法 | Route | 用途／主要 Request | 主要 Response | 權限 | 來源 |
|---|---|---|---|---|---|
| GET | `/api/account/mcp-config` | 會員取得連線／套件資訊 | MCP 端點、設定範本、安裝與檢查資訊；不回傳舊 token | 會員 | 補充 |
| GET | `/api/account/mcp-token` | 讀 token 中繼資料 | 是否有效、建立／到期／撤銷時間，不含完整 token | 會員 | 補充 |
| POST | `/api/account/mcp-token` | 首次建立 token | 完整 token 僅本次回傳、`expiresAt` | 已驗證 Email 會員 | 補充 |
| POST | `/api/account/mcp-token/rotate` | 確認重建、立即撤銷舊值 | 新 token 僅本次回傳、`expiresAt` | 已驗證 Email 會員 | 補充 |
| DELETE | `/api/account/mcp-token` | 撤銷目前 token | `ok`，立即拒絕後續使用 | 會員 | 補充 |

同時最多一個有效 token，伺服器只存雜湊，90 天到期。遺失需重建，不能再讀完整舊值。

Cloud Run 的 MCP **不是每個工具各設一個 REST route**。下列是現有規格建議的工具名；實際 MCP transport 端點路徑（如 `/mcp`）待部署時確定，不當作已存在。

| MCP tool | 功能 | 共用後端能力／限制 |
|---|---|---|
| `list_kimonos` | 查和服商品 | 商品目錄；不提供後台欄位 |
| `check_inventory` | 查商品及配件可用庫存 | 同門市／期間規則，不洩漏其他會員訂單 |
| `check_availability` | 查接待與攝影名額 | 全員名額驗證，查詢不暫留 |
| `get_photo_upload_consent`／`create_photo_upload`／`complete_photo_upload` | App-only 本機選檔、明確同意、短效 signed POST 直傳私人儲存、後端完成檢查 | 本人 MCP token 驗證；權限只回 UI metadata；最多三張，沿用網站照片庫與人物檢查；不生成、不扣額度，官網保留備援 |
| `create_try_on` | 確認後建立穿搭或場景任務 | `kind=TRY_ON/SCENE`；每日 3 次、同時 1 個；不重複扣次 |
| `get_try_on_result` | 查處理狀態與當日限時圖片 | 不回原圖，不重新生成，不入會員收藏 |
| `create_booking_draft` | 建立本人草稿與回網站入口 | 1～3 人、不 hold、不付款、不成立正式預約 |

MCP 透過服務端驗證的呼叫脈絡將會員身分交給 FastAPI 業務層；禁止以網站送入 `channel=mcp` 就取得不同限額或權限。可共用 domain service，不必為每個工具再造 `/api/mcp/...`。

MCP 圖於完成當日日本午夜到期，API 停止提供網址，worker 清理物件。依 2026-10-25 確認，私人圖片網址最長 120 秒且不得超過圖片到期時間；網址到期不移除已載入圖片，需要重新載入時以唯讀任務查詢更新，不重新生成或扣額度。UI 於圖片本身到期隱藏結果；外部客戶端保存的副本不受本站控制。詳見 MCP_SPEC.md。付款、取消、退款、核銷回網站／授權後台處理。

## 8. 門市後台、庫存與退款

對應開發表 06。資源 ID 不代表授權；所有操作都要驗所屬門市與角色。以下補充端點涵蓋今天規劃的操作，不表示每個欄位均已定稿。

| 方法 | Route | 用途／主要 Request | 主要 Response | 權限 | 來源 |
|---|---|---|---|---|---|
| GET | `/api/admin/bookings` | 日期／門市／狀態／關鍵字篩選 | 預約、旅客、付款及保留摘要 | 門市／總管 | 既有 |
| GET | `/api/admin/bookings/{bookingId}` | 查看預約詳細資料 | 旅客、造型、款式配件、庫存及交易 | 門市／總管 | 補充 |
| POST | `/api/admin/bookings/{bookingId}/check-in` | 本人到店報到；本人核對結果與到場旅客 | 後端報到時間、到場紀錄、核銷資格 | 門市／總管 | 既有 |
| POST | `/api/admin/vouchers/redeem` | 本人核對後掃碼；`qrPayload, identityConfirmed` | 一次核銷結果及紀錄 | 門市／總管 | 既有 |
| POST | `/api/admin/bookings/{bookingId}/cancel` | 商家無法履約取消；原因與通知 | 預約取消、退款待處理、票券失效 | 授權門市／總管 | 補充 |
| POST | `/api/admin/bookings/{bookingId}/weather-cancellation` | 體驗前判定室外攝影不可行 | 原因時間、全部攝影費應退額、通知狀態 | 授權門市／總管 | 補充 |
| POST | `/api/admin/bookings/{bookingId}/refunds` | 授權執行退款；政策／天候／商家取消原因 | `refundId, status, amount, currency` | 退款授權 | 補充 |
| GET | `/api/admin/refunds/{refundId}` | 查退款結果 | 處理中／完成／失敗及交易紀錄 | 門市範圍＋退款授權 | 補充 |
| GET | `/api/admin/inventory` | 依門市、商品及狀態查庫存 | 實體庫存列表與可用期間 | 門市／總管 | 補充 |
| POST | `/api/admin/inventory` | 實體和服／配件建檔 | `inventoryId`、編號及狀態 | 總管 | 補充 |
| GET | `/api/admin/inventory/{inventoryId}` | 查看單件庫存 | 所屬門市、款式狀態、保留期間 | 門市／總管 | 既有 |
| PATCH | `/api/admin/inventory/{inventoryId}` | 有限制的清潔／維修／停用狀態操作、原因 | 更新狀態及稽核紀錄 | 門市／總管 | 既有 |
| POST | `/api/admin/inventory-transfers` | 跨店調撥；庫存 ID、來源／目的店、原因 | 調撥紀錄及影響驗證結果 | 總管 | 補充 |
| POST | `/api/admin/bookings/{bookingId}/rentals` | 核銷後記錄實際交付庫存編號 | `rentalId`、出借中項目 | 門市／總管 | 補充 |
| POST | `/api/admin/rentals/{rentalId}/return` | 歸還登記與檢查 | 歸還紀錄、待檢查／清潔等狀態 | 門市／總管 | 既有 |
| GET | `/api/admin/slots` | 查接待／攝影場次及容量 | 時間、容量、已保留及剩餘 | 門市／總管 | 補充 |
| POST | `/api/admin/slots` | 建立接待／攝影場次 | `slotId` 與容量、日期時間 | 門市／總管 | 補充 |
| PATCH | `/api/admin/slots/{slotId}` | 調整場次／容量／開放狀態 | 更新結果，不損害既有預約 | 門市／總管 | 補充 |
| GET | `/api/admin/plans` | 後台方案列表，含停用資料 | 完整方案欄位及可編輯狀態 | 總管 | 補充 |
| POST | `/api/admin/plans` | 建方案、內含服務及 TWD 價格 | `planId` | 總管 | 補充 |
| PATCH | `/api/admin/plans/{planId}` | 更新方案／價格／上架狀態 | 方案新版本，不改已付款金額 | 總管 | 補充 |
| GET | `/api/admin/kimonos` | 後台商品列表，含停用資料 | 商品、展示圖片關聯 | 總管 | 補充 |
| POST | `/api/admin/kimonos` | 建和服商品、圖片關聯 | `kimonoId` | 總管 | 補充 |
| PATCH | `/api/admin/kimonos/{kimonoId}` | 更新商品、圖片或販售狀態 | 商品新版本 | 總管 | 補充 |
| GET | `/api/admin/accessories` | 後台配件列表，含停用資料 | 配件、價格及圖片 | 總管 | 補充 |
| POST | `/api/admin/accessories` | 建可售配件與價格 | `accessoryId` | 總管 | 補充 |
| PATCH | `/api/admin/accessories/{accessoryId}` | 更新配件價格／圖片／上架狀態 | 配件新版本 | 總管 | 補充 |
| GET | `/api/admin/stores` | 後台門市列表，含停用資料 | 所屬授權範圍內完整門市資料 | 門市／總管 | 補充 |
| POST | `/api/admin/stores` | 建立門市、時區、營業資訊 | `storeId` | 總管 | 補充 |
| PATCH | `/api/admin/stores/{storeId}` | 更新門市資訊 | 門市新版本 | 總管 | 補充 |
| GET | `/api/admin/photography-options` | 後台攝影選項列表，含停用資料 | 價格、費用拆分、季節及場次關聯 | 門市／總管 | 補充 |
| POST | `/api/admin/photography-options` | 建攝影方案、季節／場景／輸出及費用拆分 | `optionId` | 總管或獲授權門市 | 補充 |
| PATCH | `/api/admin/photography-options/{optionId}` | 維護攝影選項、加價及適用日期 | 更新結果 | 總管或獲授權門市 | 補充 |

後台目錄列表可共用公開目錄的底層查詢服務，但須使用後台權限取得停用與完整欄位，不要讓公開 API 洩漏未上架資料。編輯表單可從後台列表資料載入；未來若資料量需要，可另加單筆後台查詢，不為每個欄位另做 route。

不提供任意 `PATCH booking.status=PAID/REDEEMED` 來跳過金流或核銷，也不以一般庫存 PATCH 隨意修改有效保留。核銷／出借／歸還／清潔有合法狀態轉移；歸還後完成整備才回可用。未到場與 hold 到期由可靠背景工作根據伺服器時間處理，不要求會員開著網頁。

天候退還全部單獨加購及內含攝影費，不扣相簿備貨，租借及 QR 保持有效；商家無法履約取消則全額退款，不能套用會員七天不退政策。

## 9. Request／Response 範例

下列 ID、網址及金額均為示例。這些是建議契約，不是從已運作 API 抓取的資料。

### A. 方案列表：像老師作業的景點列表

```http
GET /api/plans?city=TOKYO&page=0
```

```json
{
  "nextPage": 1,
  "data": [
    {
      "id": "plan_001",
      "name": "高級振袖方案",
      "city": "TOKYO",
      "currency": "TWD",
      "price": 2400,
      "includedServices": ["和服租借", "基本著裝"]
    }
  ]
}
```

### B. 新增收藏：沒有 AI 圖也可收藏

```http
POST /api/looks
Authorization: Bearer <Firebase ID token>
Content-Type: application/json
Idempotency-Key: <unique-action-key>
```

```json
{
  "planId": "plan_001",
  "kimonoId": "kimono_012",
  "accessoryIds": ["bag_002"],
  "sceneId": null,
  "generationId": null
}
```

成功回 `201`，回傳 `lookId`、收藏內容與當前 TWD 價格。不傳 `userId` 指定收藏主人，後端從驗證身分決定。

### C. 前往付款：不是一建草稿就佔名額

```http
POST /api/availability/holds
Authorization: Bearer <Firebase ID token>
Idempotency-Key: <unique-action-key>
```

```json
{
  "draftId": "draft_001",
  "quoteToken": "quote_signed_value"
}
```

```json
{
  "data": {
    "holdId": "hold_001",
    "status": "HELD",
    "serverTime": "2026-10-20T01:00:00Z",
    "expiresAt": "2026-10-20T01:10:00Z",
    "currency": "TWD",
    "total": 2700
  }
}
```

只有整筆所有旅客資源都成功才回成功；缺一項即拒絕，不部分保留。前端顯示日本時間，儲存與傳輸建議 UTC ISO 8601。

### D. 提交付款，結果待確認

```http
POST /api/bookings
Authorization: Bearer <Firebase ID token>
Idempotency-Key: <unique-payment-action-key>
```

```json
{
  "holdId": "hold_001",
  "quoteToken": "quote_signed_value",
  "prime": "tappay_prime_from_sdk",
  "contact": {"name": "示例旅客", "email": "guest@example.com", "phone": "+886900000000"},
  "cancellationPolicyVersion": "2026-10-16",
  "acceptedCancellationPolicy": true
}
```

後端確認中可以回 `202`：

```json
{
  "data": {
    "orderNo": "order_001",
    "paymentStatus": "PAYMENT_PENDING",
    "bookingNo": null
  }
}
```

前端再 `GET /api/orders/order_001`。只有後端已確認付款且有效保留轉正式後，才能顯示成功、正式 `bookingNo`、會員 QR 與寄成功信。

## 10. 共用錯誤與冪等規則

錯誤沿用技術規格，以下 HTTP 對應為本次建議：

```json
{
  "error": {
    "code": "INVALID_GUEST_COUNT",
    "message": "每筆預約限 1～3 人",
    "field": "guests",
    "requestId": "req_example"
  }
}
```

| HTTP | 使用情況 |
|---|---|
| 200 / 201 | 查詢／更新成功、資源已建立；不等於外部付款一定成功 |
| 202 | 已接受非同步任務、付款或刪帳尚處理中 |
| 400 | 請求不完整或業務指令無效 |
| 401 | 未登入、憑證無效／過期 |
| 403 | 未驗 Email、無權限、缺必要照片同意；可用一致的 404 隱藏別人的資源 |
| 404 | 資源不存在或不可向呼叫者揭露 |
| 409 | 額滿、庫存不足、hold 過期、版本／狀態衝突、刪帳仍有未結事項 |
| 422 | 欄位不合法，含旅客不是 1～3 人或清單不一致 |
| 429 | 生成額度不足或請求過於頻繁 |
| 502 / 503 | 外部服務異常／暫時無法提供服務，不洩漏金鑰與供應商內部資料 |

所有會生成、保留資源、扣款、取消、退款、核銷的 mutation 都需安全重試與冪等性。本站統一建議使用 `Idempotency-Key`：同會員、同操作、同鍵同內容回原結果；同鍵不同內容回衝突。金流 callback 則用供應商事件／交易識別去重。一般 PATCH 使用版本或等價併發檢查，避免跨裝置覆蓋。

## 11. 建議實作順序與期末界線

1. 01 基礎：health、商品／方案／門市、account、權限。
2. 02 試穿：sessions、upload-url、validate、generations、jobs、場景及圖片生命週期。
3. 03 MCP：token、連線資訊及工具，共用已完成業務能力。
4. 04 收藏：looks 與 2～3 方案比較，商品可直接收藏。
5. 05 交易：草稿→quote→hold→提交付款→查單→正式預約／QR／成功信→取消退款。
6. 06 後台：列表、門市權限、報到核銷、實體庫存出借歸還、商品名額與授權退款。
7. 07～08：端到端、真機、跨裝置、併發與失敗恢復驗收及展示。

11/16 的行事曆、最近可預約日期、FAQ 搜尋、三語系與體驗前提醒另列後續設計。它們不全需要新增 API：例如 `.ics` 下載或 FAQ 搜尋的 route 可到該階段再定；體驗前提醒主要是排程工作。成功 Email、圖片到期清除、hold 查核、未到場處理也不應為了畫面每個動作各新增一個公開 route。

## 12. 與原規格需要同步的介面決策

- `plans/compare` 從只有 planIds 擴充搭配識別，以符合收藏中的配件、圖片與總價比較。
- 補上「預製圖沒有 jobId」的場景生成入口。
- 明確 `POST /api/bookings` 為唯一提交付款入口，訂單待確認與正式預約成立分開。
- token、查單、QR、退款與後台管理等補充路由仍是本表提案，原技術規格尚未逐條回寫。
- API 路由不能只靠 HTTP 方法授權；MCP token 不得呼叫網站付款／取消／退款／核銷，網站 Firebase token 也不能自行指定生成通道。

實作前把上述決策同步至 OpenAPI／Pydantic 與原技術規格；不要同時保留互相矛盾的 request 格式。確切圖像編輯模型仍待既有流程的驗證／定案；MCP 圖片網址 TTL／重發政策已依 2026-10-25 確認同步至本表與 MCP_SPEC.md。


## 2026-10-23 場景生成決策

- /try-on 每位旅客在腰帶區下方提供「場景」下拉選單：不變更（預設）、櫻花、寺廟；男女皆適用。
- 先確認並完成 Virtual Try-On，再另行確認場景生成；選擇場景不自動呼叫 API。場景未生成也可直接預約。
- 以原始 TRY_ON 結果交由 Vertex AI `gemini-nano-banana-2.1`（global）變換背景；固定櫻花步道／日式寺廟庭院文字提示，要求保留人物、臉部、姿勢、和服與腰帶，僅調整背景、環境光與陰影，畫面提示 AI 仍可能改變細節。
- 試穿與場景共用網站每日 5 次額度（日本午夜重設），每次新任務各計 1 次。與現有試穿一致，失敗不自動重送，重新確認重試另用 1 次額度。
- 同會員、同原始試穿圖、同場景、同提示／模型版本已有有效結果時直接重用；同一請求及進行中任務不重複扣次。不提供強制重新生成選項。
- 每次場景生成均引用原始 TRY_ON 結果；禁止使用 SCENE 結果作為另一場景的輸入。驗證擁有者、來源有效期限及人物同意，失效來源不扣額度。
- 原圖與場景結果分開私有保存，各於完成後保存 7 天。場景失敗仍顯示原始試穿圖；切回不變更顯示原圖；刪除原始試穿圖不連帶刪除既有場景結果。
- 收藏優先保存目前選取且已完成的場景結果 generationId；未完成時沿用原始試穿圖。場景不改變和服、腰帶明細或預約費用。
- 公開 GET /api/scenes 提供場景選項；POST /api/try-on/jobs/:jobId/scene-generations 接收 sceneId（CHERRY_BLOSSOM／TEMPLE）、confirmed:true、Idempotency-Key，須會員登入。回應沿用 job，新增 sceneId、parentJobId。
