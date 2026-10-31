> 歷史功能設定參考：目前啟動、路徑與操作請見 [現行文件索引](../README.md)。

# Firebase 會員登入

## 本地啟動與操作

在 backend 資料夾依 README 啟動 FastAPI，使用 `http://localhost:8000/#/account`。若使用其他埠，替換 8000 即可。Firebase Console → Authentication → Settings → Authorized domains 應包含 `localhost`。前端由 FastAPI 提供，直接開啟 HTML 檔無法使用會員 API。

1. 點「會員 → 建立帳號」，輸入 Email、密碼與確認密碼。註冊後自動寄驗證信，進入驗證畫面。
2. 點信件中的 Firebase 驗證連結，再回網站點「我已完成驗證」。沒有收到時可重新寄送；頻率受 Firebase 限制。
3. 登出後重新登入，確認會員中心顯示遮罩 Email 與驗證狀態。
4. 登入頁點「忘記密碼」，填 Email，由 Firebase 寄送重設連結；密碼變更在 Firebase 頁面完成。
5. 從方案頁點會員，完成登入後返回原方案或列表，保留網址上的篩選條件。其餘尚未開發的私人功能仍為線框，不代表完成授權或交易功能。

驗證信與重設信的實際收件，需使用自己能接收的信箱手動驗證。

## 設定與資料

- `frontend/js/firebase-config.js` 僅放公開的 Firebase Web 設定。
- 後端 `.env` 放 `FIREBASE_PROJECT_ID` 與 `FIREBASE_SERVICE_ACCOUNT_PATH`（Firebase 私鑰 JSON 的絕對路徑）。JSON 必須保存在 frontend 以外，不能提交版本庫或公開部署。此專用變數避免 Firebase 憑證覆蓋 Vertex AI 使用的本機 gcloud ADC；舊環境未設定時仍沿用 Firebase Admin 的預設憑證機制。
- Firebase SDK 管理登入狀態與憑證更新；本站不保存密碼，不自製 JWT。
- `PUT /api/account` 搭配 `Authorization: Bearer <Firebase ID token>` 與空 JSON `{}`，冪等同步會員；`GET /api/account` 取得本人資料。Email 未驗證仍可登入，同步狀態如實顯示。
- FastAPI 檢查簽章、專案、期限、撤銷與 Firebase 停用狀態。缺少或無效憑證回 401、驗證服務不可用回 503、本站停用會員回 403。
- RDS `users` 保存 UID、Email、驗證狀態與本站角色。新會員固定 CUSTOMER，重複同步不覆寫角色與停用狀態。前端不得指定身分或角色。
- 收藏已接上會員驗證，操作說明見 LOOKS.md。付款、MCP 與刪帳端點尚未實作；後續必須各自加入身分、Email 驗證及資料存取檢查。

## 測試

```powershell
$env:RUN_DATABASE_TESTS='1'
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

若要額外檢查真實 Firebase：

```powershell
$env:RUN_FIREBASE_TESTS='1'
.venv/Scripts/python.exe -m unittest discover -s tests -p test_firebase_live.py -v
```

真實測試會建立一次性 example.com 帳號、驗證登入與停用拒絕，最後刪除該帳號，RDS 寫入回滾；不會寄送 Email。只有明確設定 RUN_FIREBASE_TESTS 才執行。
