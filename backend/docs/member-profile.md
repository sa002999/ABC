# 會員資料與手機驗證

部署前先從 backend 執行 `.venv/Scripts/python.exe manage.py migrate`，套用 `020_member_profile.sql`。
會員姓名以本站資料庫為準；登入同步只更新 Email 與其驗證狀態，不覆寫編輯後姓名。
`PATCH /api/account` 只允許 `displayName`；Email 唯讀。
`POST /api/account/phone` 接收 `phoneToken`，後端驗證 Firebase 簽章、撤銷狀態、phone provider、驗證時間、手機格式，並要求主會員最近五分鐘以密碼重新驗證。
手機唯一約束保證不能同時綁定兩位會員；更換失敗不移除原號碼。已成功使用的簡訊證明不能重新綁定至別人或覆寫之後的新號碼。

## Firebase Console 設定

1. Authentication → Sign-in method → Phone：啟用。
2. Authentication → Settings → SMS region policy：允許 Taiwan (TW) 與 Japan (JP)。目前只允許 TW 時，日本手機無法接收驗證簡訊。
3. Authentication → Settings → Authorized domains：保留 `kinu-tabi.firebaseapp.com`、`kinu-tabi.web.app`，並加入實際部署網站的 hostname。`authDomain` 和使用者開啟網站的 hostname 不一定相同。
4. 確認專案符合正式驗證簡訊的 Firebase 計費與配額要求。

不需要自行建立 reCAPTCHA site key：網頁透過 Firebase `RecaptchaVerifier` 自動取得設定並顯示可見的人機驗證。
獨立 `phone-verification` Firebase App 使用記憶體 session；手機只在此 session 完成驗證，不 link 到 Email 會員，成功後登出驗證 session。
Firebase 會保留 phone-only Auth 使用者，這不是本站會員，也不能通過本站需要 Email 的登入驗證。不要把它手動合併至 Email 會員。

## 本機與正式測試

官方 Phone Auth 文件說明 localhost 不支援正式手機驗證網域；把 localhost 加入授權清單仍不足以保證真實簡訊測試成功。
正式 reCAPTCHA 與真實簡訊請從已授權的 HTTPS 網站測試。
開發可使用 Authentication → Sign-in method → Phone → Phone numbers for testing 設定測試號碼與六位驗證碼；這些號碼不會收到真實簡訊。
本程式不在正式環境停用 reCAPTCHA，不內建測試驗證碼。若本機 SDK 仍拒絕網域，改在授權 HTTPS 測試站使用測試號碼，或另行使用 Firebase Auth Emulator。

驗收：姓名保存後重新登入仍保留；Email 驗證後刷新顯示已驗證；綁定手機不切換主會員；錯誤／到期碼不保存；相同手機第二會員綁定失敗；更換新手機失敗仍保留舊號碼；新預約帶入會員聯絡資料，舊草稿不變。

官方文件：https://firebase.google.com/docs/auth/web/phone-auth
