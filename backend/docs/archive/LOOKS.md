> 歷史功能設定參考：目前啟動、路徑與操作請見 [現行文件索引](../README.md)。

# 我的造型收藏

## 本地操作

重新啟動 FastAPI，開啟 `http://localhost:8000/`（若使用其他埠請替換）。

1. 探索方案 → 方案詳情 → 加入收藏。未登入時先登入，保留方案與原篩選，返回後接續同一次收藏。
2. 我的造型 → 顯示本人收藏，圖片由商品目錄／CloudFront 提供。取消收藏不會刪除商品圖、原圖或生成圖。
3. 編輯搭配 → 更新此收藏 → 確認更新原收藏。若其他裝置已修改，會拒絕舊版本，須重新載入再確認。
4. 選擇 2～3 筆不同和服的收藏 → 比較所選方案。比較列出目前 TWD 方案價格、包含內容、門市，允許移除比較欄位並返回收藏。
5. 同帳號在另一個瀏覽器或裝置登入，重新載入即可取得相同收藏。頁面不以瀏覽器本地收藏清單作為資料來源。

收藏不要求 Email 已驗證，付款與 MCP 的 Email 驗證規則仍須在後續功能實作。收藏／比較不保留庫存，也不會觸發 AI 或建立預約。

## 範圍

目前保存方案、和服，允許沒有 AI 圖就收藏。價格不寫入收藏，而是每次從目前方案讀取。未上架方案或商品不可用時，保留收藏並標示狀態，停止比較；不公開停用商品的內容與圖片。

配件、場景、AI 生成圖尚未接上；非空 accessoryIds／sceneId／generationId 會回 422，不保存無法驗證的來源。等這些資料表與 API 完成後，再加入對應驗證、本人生成圖來源與到期回退規則。目前圖片均明確標示為商品圖。

## API

所有下列端點皆使用 Firebase ID token，且只可操作登入者自己的收藏。本站停用帳號回 403；其他人的收藏與不存在的收藏一律回 404。私人回應使用 no-store。

| 方法 | 路徑 | 說明 |
|---|---|---|
| POST | /api/looks | 新增收藏，首次 201，重複搭配 200 並沿用同一 lookId |
| GET | /api/looks | 分頁；page 從 0 起、pageSize 預設 12／最多 50，可用 planId 篩選 |
| GET | /api/looks/{lookId} | 本人單筆收藏，供重新載入與編輯 |
| PATCH | /api/looks/{lookId} | 完整搭配與 version，成功版本加一，版本或重複搭配衝突回 409 |
| DELETE | /api/looks/{lookId} | 只取消此收藏，不刪圖片 |
| POST | /api/plans/compare | `{lookIds: [UUID, UUID]}`，2～3 筆本人收藏，按輸入順序回傳陣列 |

POST/PATCH 搭配欄位：`planId`、`kimonoId`、`accessoryIds: []`、`sceneId: null`、`generationId: null`。PATCH 另加 `version`。前端不得指定 userId、價格或其他額外欄位。

POST 支援 UUID 格式的 `Idempotency-Key`，同會員、同動作鍵重送沿用現有收藏；相同動作鍵換內容回 409。同搭配亦有資料庫唯一限制。取消收藏會刪除此收藏與其動作鍵紀錄，之後可重新收藏。這不是付款或庫存保留的冪等規格。

登入接續只暫存一個尚未完成的操作與選擇，放在該分頁 sessionStorage，最長 30 分鐘；不保存匿名收藏、密碼、憑證或圖片。網址上的 saveLook 必須符合該分頁的操作紀錄才會接續，不會只因收到一個網址就自動收藏。登入失效、儲存失敗或無法使用 sessionStorage 時，可重新點擊收藏。

## 初始化與測試

```powershell
.venv/Scripts/python.exe manage.py migrate
$env:RUN_DATABASE_TESTS='1'
.venv/Scripts/python.exe -m unittest discover -s tests -p test_looks.py -v
```

測試包含登入要求、會員隔離、停用會員、重複與重送、錯誤搭配、版本衝突、目前價格、下架保留、取消收藏不刪圖片、分頁及比較限制。資料變更會以交易回滾。
