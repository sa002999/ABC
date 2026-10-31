> 歷史功能設定參考：目前啟動、路徑與操作請見 [現行文件索引](../README.md)。

# 商品與方案目錄

目前使用 RDS PostgreSQL 保存和服、方案、方案適用門市及商品圖片關聯。這是本地開發功能；價格、服務內容及分類都屬測試資料。

| 商品編號 | 測試名稱 | 門市 | 測試價格（TWD） | 風格 |
|---|---|---|---|---|
| RKH0002 | 紫藤花語和服體驗 | 京都測試門市 | 1500 | ELEGANT／典雅 |
| RKH0057 | 粉映花枝和服體驗 | 京都測試門市 | 1800 | ROMANTIC／柔美 |
| RKH0103 | 墨葉留白和服體驗 | 東京測試門市 | 2100 | MODERN／俐落 |

初始化指令（在 backend 執行）：

```powershell
uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt
.venv/Scripts/python.exe manage.py migrate
.venv/Scripts/python.exe manage.py seed-demo
.venv/Scripts/python.exe manage.py seed-catalog
```

`seed-catalog` 使用固定 UUID，重跑不覆寫既有商品。原始 PNG 保留於 `assets/kimono/`；展示用 WebP 產生於 `catalog-media/kimono/`，需讓執行本地服務的電腦保有這些檔案。預設模特兒 `assets/default models/person.jpg` 不會當作商品圖或預製穿搭圖匯入，也不透過商品圖片 API 公開。

商品圖片支援經驗證後發布至私有 S3，並由 CloudFront 提供；設定與發布指令見 [STORAGE.md](STORAGE.md)。未發布的圖片保留本地 FastAPI 來源。預製穿搭圖尚未提供，因此切換按鈕會標示不可用。

## API

- `GET /api/plans`：方案列表。支援 `city`、`store`（UUID）、`style`、`audience`、`minPrice`、`maxPrice`、`keyword`、`sort`、`page` 與 `pageSize`。
- `GET /api/plans/{UUID}`：單一方案，含商品、圖片、適用門市、TWD 價格與包含內容。
- `GET /api/kimonos`：和服目錄。支援 `city`、`store`、`plan`、`page` 與 `pageSize`。
- `GET /api/kimonos/{UUID}`：單件和服與圖片。
- `GET /api/catalog-assets/{UUID}`：經上架狀態檢查後提供本地 WebP，或回 302 至已發布的 CloudFront 圖片，不接受任意檔案路徑。

方案列表回傳 `{data, total, nextPage}`。`page` 從 0 開始、`pageSize` 預設 12、最多 50；沒有下一頁時 `nextPage=null`。排序可用 `recommended`、`priceAsc`、`priceDesc`。查詢條件交集不符回空列表；不合法條件回 422；不存在或下架資源回 404。

和服、方案或所有適用門市下架後，API 不再提供該方案或商品圖片。已知公開 CloudFront 商品網址與快取仍可能存取，撤回方式見 STORAGE.md。使用參數化 SQL，價格為整數 TWD，圖片紀錄明確區分 `PRODUCT` 與 `STYLED`。

## 前端驗證

啟動 FastAPI 後開啟 `http://127.0.0.1:8000/#/plans`。篩選、排序及清除條件會更新 Hash 網址；重新整理可還原。進入方案詳情再返回，保留原篩選。列表支援自動載入與「載入更多」按鈕備援，失敗可重試。

收藏修改與收藏比較已接上會員 API，見 [LOOKS.md](LOOKS.md)。日期名額、庫存與實體編號、配件加購、AI 生成及預約付款仍待實作，這些操作按鈕保持不可用。

整合測試沿用 README 的 `RUN_DATABASE_TESTS=1` 指令；測試會驗證三套門市分配、複合條件、分頁、關鍵字、圖片、下架狀態與路徑限制，資料更動以交易回滾。
