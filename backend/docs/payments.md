# 官網 Sandbox 付款（2026-11-07）

目前完成官網報價 → 10 分鐘暫留 → TapPay 非 3D 信用卡 Sandbox → Record 查核 → 正式測試預約 → 成功頁／會員預約列表與明細。正式金流、3D／錢包、確認 Email、QR 與取消退款執行尚未開放。

## 啟動與設定

後端 `.env` 沿用 `TAPPAY_PARTNER_KEY`、`TAPPAY_MERCHANT_ID`、`TAPPAY_ENDPOINT`；唯一允許端點為 `https://sandbox.tappaysdk.com/tpc/payment/pay-by-prime`。前端 `.env.local` 使用 `VITE_TAPPAY_APP_ID`、`VITE_TAPPAY_APP_KEY`、`VITE_TAPPAY_SERVER_TYPE=sandbox`。Partner Key 不可放入任何 VITE 變數。

先執行 `python manage.py migrate`，再依 INTEGRATION.md 啟動 API 與 Vite。付款另開一個終端，在 backend 執行：

```powershell
.\.venv\Scripts\python.exe manage.py payment-reconcile
```

此程序每 15 秒處理至多 20 筆待確認／待請款訂單，同單至少間隔 45 秒。只查 Record API，不呼叫付款 API，不啟動 AI worker。Ctrl+C 停止。會員查看原單也可觸發相同限頻查核。

## 交易規則

- `POST /api/bookings` 是唯一付款入口。接收 holdId、quoteToken、Prime、acceptedPolicy、policyVersion，必須有 UUID Idempotency-Key；Email 驗證與會員持有權由後端檢查，MCP token 無法使用。
- 訂單與 PAYMENT_PENDING hold 先提交資料庫，再送出一次 Pay by Prime。同會員同 key 不同內容拒絕；同 hold 換 key 仍回原單。Prime、卡號、CVV、card_secret 與供應商完整回應不保存。
- 金額、聯絡資料、旅客與搭配從後端暫留／草稿取出，保留購買快照。已過報價的 5 分鐘期限仍可在有效 hold 的 10 分鐘內付款，不要求使用者在兩個不同倒數內操作。
- 取消政策版本 `cancellation-7days-v1`：依日本當地場次開始時間，超過 7×24 小時取消全退，等於或少於 7×24 小時不退。付款前另行勾選同意；只保存同意紀錄，此階段不執行退款。
- 使用後端 Record API，優先以 rec_trade_id 查詢；回應遺失無 ID 時依預先保存的唯一 bank_transaction_id 查詢。必須核對 merchant、bank_transaction_id、TWD、金額與 rec_trade_id；供應商若帶 order_number 也必須相符。
- AUTH 轉 AUTHORIZED，與全員有效配置在同一交易中轉 RESERVED 並建立唯一預約；OK 轉 PAID，沿用同一預約。待請款與已請款分開呈現。
- 查無紀錄、連線逾時或待確認不會重送付款，也不因 10 分鐘到期釋放。會員可從原 hold 或「我的預約」中的未結訂單恢復；交易無法判定時保留原單等待查核。
- 已確認失敗才釋放；資料不符轉 REVIEW_REQUIRED；已授權但缺少有效配置轉 REFUND_REQUIRED，保留資料供後續人工處理，不冒充預約成功或退款完成。
- 有訂單的失敗 hold／配置保留，不走一般暫留七日清除；避免清理外鍵失敗並保留交易稽核資料。交易資料保存期限另於正式營運前確定。

## 網站驗收

1. 使用已完成 Email 驗證的會員登入，依序完成預約、聯絡資料與報價。
2. 確認報價並建立暫留。付款面板顯示門市、日本時間、費用明細、總額、聯絡資料及取消政策。
3. 勾選政策後，使用 TapPay 官方 Sandbox 測試卡完成付款；勿填真實卡片。授權成功後開啟成功頁，再到「我的預約」查回同一預約。
4. 重整暫留或訂單頁可恢復；付款未確認時只查單。票券、取消退款維持停用。

## 驗證紀錄

- 前端 TypeScript／Vite build、44 項測試通過，包括雙擊只提交一次、斷線後先恢復原單、政策／逾期阻擋。
- 後端一般測試 122 項中 47 通過、75 opt-in 略過；新增付款測試使用可提交的連線專屬 TEMP 表，不寫入本人會員資料。
- 付款資料庫測試涵蓋一次授權／原單重送／請款沿用預約、未知交易、金額不符、已確認失敗釋放、需退款例外、政策與 Email 拒絕、本人隔離、no-store。
- 四個獨立連線同時以不同 key 提交同一 hold，只送一次付款、只建一筆預約；測試獨立 schema 完成後清除。
- 真實 Sandbox 使用官方 Test Prime 與虛構聯絡資料驗證 AUTHORIZED 與預約成立。本次排查共送出三筆 Sandbox 測試交易，沒有真實款項；外部 Sandbox 紀錄保留於 TapPay Portal，本地使用 TEMP 表並於連線關閉清除。
- 瀏覽器確認未登入的官網預約頁正常顯示 Sandbox 文案；另以暫時測試頁載入現有 PaymentFields，確認實際 TapPay SDK 的卡號、有效期限、安全碼欄位可顯示，未輸入卡片、未呼叫 getPrime，測試頁已移除。登入後真實前端 getPrime 與完整人工點選仍需會員驗收；後端官方 Test Prime 驗證不等於瀏覽器端到端驗收。
- 原有三人含腰帶報價／整筆暫留與恢復、收藏腰帶價格變動、部分草稿驗證及到期／付款待確認保護均通過；付款開放後同步更新了原測試中「付款永久停用」的舊預期。

官方契約：[Backend](https://docs.tappaysdk.com/tutorial/en/back.html)、[Reference](https://docs.tappaysdk.com/tutorial/en/reference.html)。
