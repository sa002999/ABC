# KINU TABI｜頁面路由與使用者流程圖

更新：2026-10-16。依[最新會員體驗](./04-member-flow-decisions.md)、[產品規劃](./01-product-experience.md)與[API 開發表](./06-api-routes.md)整理；這是待實作規劃，不表示頁面或 API 已完成。

這類圖稱為 **使用者流程圖（User Flow）／頁面路由流程圖**。頁面用方框、操作用圓角節點、條件用菱形，箭頭表示跳轉或狀態回饋。樹狀圖／網站地圖主要呈現上下層關係；這份流程有返回、失敗與分支，適合流程圖。

方框中的 `/plans`、`/booking` 是 React 前端頁面路徑；`GET /api/plans` 是後端 API。一個頁面可呼叫多個 API，不需要一頁對一支 API。

## 圖一：登入、返回原位置與登出

```mermaid
flowchart TD
    home["首頁 /"]
    browse["方案 /plans"]
    action(["點收藏、預約、上傳或生圖"])
    auth{"已登入？"}
    login(["Firebase Email／密碼登入"])
    error["登入錯誤提示"]
    resume(["返回原操作並保留選擇"])
    account["會員頁 /account"]
    logout(["登出"])
    home --> browse
    browse --> action
    action --> auth
    auth -->|"否"| login
    auth -->|"是"| resume
    login -->|"失敗"| error
    error -->|"重試"| login
    login -->|"成功"| resume
    home -->|"會員入口，未登入先登入"| account
    resume -->|"依操作接續，不自動生圖"| browse
    account --> logout
    logout --> home
```

登入可以用共用彈窗或獨立頁，現行規格未固定 `/login`，因此不自行宣告已有這條頁面路由。登入成功回原入口，不一律送到會員頁。錯誤在登入介面提示，不為了仿照範例額外增加 `/ohoh`。圖中「返回方案」代表原入口的例子，試穿／收藏／預約入口也須保留自己的返回位置。

## 圖二：方案、試穿、收藏與預約

前提：需要會員權限的操作套用圖一；匿名可公開瀏覽與比較外拍方案。

```mermaid
flowchart TD
    home["首頁 /"]
    plans["探索方案 /plans"]
    detail["方案詳情 /plans/:planId"]
    tryOn["試穿 /try-on"]
    generate(["確認穿搭或場景生成"])
    result["試穿結果，同頁顯示"]
    recover["保留搭配，可重試或略過"]
    save(["加入收藏，選用"])
    looks["我的造型 /looks"]
    compare["比較 /looks/compare"]
    booking["預約 /booking"]
    hold(["確認全員資源，暫留 10 分鐘"])
    pay(["TapPay 信用卡付款"])
    pending["付款確認中"]
    complete["完成 /booking/complete/:bookingNo"]
    mine["我的預約 /bookings/:bookingNo"]
    home --> plans
    plans --> detail
    detail -->|"直接預約"| booking
    detail -->|"選用試穿"| tryOn
    detail -->|"商品也可收藏"| save
    tryOn --> generate
    generate -->|"成功"| result
    generate -->|"失敗或額度不足"| recover
    recover -->|"確認重試"| generate
    recover -->|"略過"| booking
    result -->|"不收藏也可預約"| booking
    result --> save
    save --> looks
    looks -->|"選 2～3 套"| compare
    compare -->|"選定"| booking
    looks -->|"直接選定"| booking
    booking -->|"Email 已驗證、確認報價政策"| hold
    hold -->|"整筆暫留成功"| pay
    pay -->|"後端查核中"| pending
    pay -->|"失敗，確認交易後重試"| booking
    pay -->|"付款成功且轉正式保留"| complete
    pending -->|"確認成功且正式保留"| complete
    pending -->|"確認未成功"| booking
    complete -->|"QR 與成功 Email"| mine
```

- 試穿與收藏是可選操作，不是預約前提；本人照片可改用商店模特兒，所有即時生成仍先登入並確認。
- 場景可在試穿／商品／收藏入口接續；預製圖可直接用於符合規則的場景合成。詳細圖片與配件分支依原體驗文件，本圖不重複展開。
- 報價或全員庫存／名額不足時留在預約流程提示修正，不能進付款。草稿及收藏不保留資源。
- 付款確認中不直接釋放；已扣款但無法成立預約時進處理通知及全額退款，不走成功頁。

## 圖三：外部 AI agent 與 MCP 草稿回網站

```mermaid
flowchart TD
    account["會員頁 /account"]
    config["MCP 設定 /account/mcp"]
    token(["驗證 Email，建立本人 token"])
    setup(["首次在自己的 agent 載入設定"])
    agent["會員自己的 AI agent"]
    tools(["MCP 查商品、名額、照片與試穿"])
    draft(["確認後建立本人預約草稿"])
    web["網站 /booking，帶入草稿"]
    verify(["網站登入並驗草稿歸屬"])
    review(["重驗價格、商品與全員名額"])
    pay(["進付款才暫留 10 分鐘"])
    account --> config
    config --> token
    token --> setup
    setup --> agent
    agent --> tools
    tools -->|"查結果並選定"| draft
    draft -->|"不保留商品或名額"| web
    web --> verify
    verify --> review
    review --> pay
```

`/booking` 如何攜帶 draftId（例如查詢參數）是實作契約，現有文件未固定新頁路徑；連結不放 MCP token。token 不能當網站登入憑證。已設定 agent 後可直接使用，撤銷／重建／刪帳後舊 token 即失效。

MCP 每日 3 次、同時 1 個任務，圖片當天日本午夜刪除且不入網站收藏；網站每日 5 次、圖完成起 7 天。agent 照片處理同意及每次生成確認分開；正式付款、取消、退款與核銷回網站／授權後台。

## 圖四：到店報到、核銷與歸還

以下後台方框是畫面功能名稱，**尚未固定前端 `/admin/...` 頁面路徑**；後端 API 已列於 API 開發表。

```mermaid
flowchart TD
    ticket["會員預約 /bookings/:bookingNo"]
    show(["會員本人到指定門市出示票券"])
    staff["門市後台：報到與本人核對"]
    allowed{"期限內已記錄報到？"}
    redeem(["連線後端，一次核銷整筆"])
    noShow["逾期未報到，標記未到場"]
    handover(["交付並記錄實體庫存編號"])
    rental["出借中"]
    returned(["登記歸還"])
    cleaning["檢查、清潔或維修"]
    ready["整備完成，可再次分配"]
    ticket --> show
    show --> staff
    staff --> allowed
    allowed -->|"是，含期限當下"| redeem
    allowed -->|"否"| noShow
    redeem --> handover
    handover --> rental
    rental --> returned
    returned --> cleaning
    cleaning -->|"完成整備"| ready
```

報到期限為日本時間預約開始後 30 分鐘（含），期限內先記錄報到，排隊後仍可核銷。QR 每 5 分鐘更新，不能代替本人核對或延長報到期限。跨門市、重複核銷及取消預約票券均拒絕；部分旅客未到場留紀錄，不拆票。未到場解除商品保留後須由門市確認才恢復分配，核銷也不等於庫存立即可用。

## 頁面與 API 對照

| 前端頁面／操作 | 主要呼叫的後端 API |
|---|---|
| `/plans`、`/plans/:planId` | `GET /api/plans`、`GET /api/plans/{planId}`、商品與配件目錄 |
| `/try-on` | sessions、upload-url、validate、generations、jobs；場景與額度查詢 |
| `/looks` | `GET/POST /api/looks`、`PATCH/DELETE /api/looks/{lookId}` |
| `/looks/compare` | `POST /api/plans/compare`，帶 2～3 筆本人搭配識別 |
| `/booking` | booking-drafts、pricing/quote、availability/holds、`POST /api/bookings` |
| 付款確認中介面 | `GET /api/orders/{orderNo}`；尚未成立時不使用不存在的 bookingNo |
| `/booking/complete/:bookingNo`、`/bookings/:bookingNo` | `GET /api/bookings/{bookingNo}`、voucher、取消試算／取消 |
| `/account`、`/account/mcp` | account、generation-usage、mcp-config、mcp-token 管理 |
| 門市後台報到核銷 | admin/bookings、check-in、vouchers/redeem |
| 門市後台出借歸還 | rentals、return、inventory |

表內縮寫對應完整路徑見 [06 API Route 開發表](./06-api-routes.md)。本圖只展開主要旅程，取消、退款、刪帳及全部失敗情境仍依原產品與技術規格，不因省略而取消需求。
