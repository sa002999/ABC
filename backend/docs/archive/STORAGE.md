> 歷史功能設定參考：目前啟動、路徑與操作請見 [現行文件索引](../README.md)。

# 商品圖片：S3 與 CloudFront

## 本地設定

`backend/.env` 使用既有資源（憑證不要放進前端，也不要貼到聊天）：

```dotenv
AWS_REGION=ap-southeast-2
S3_BUCKET=kinu-tabi-app-images-2026
CLOUDFRONT_DOMAIN=dkwx35rlj68fs.cloudfront.net
AWS_PROFILE=kinu-tabi-local-dev
```

目前本地環境使用已建立的 `kinu-tabi-local-dev` profile，不需在 `.env` 重複填寫 access key。三張商品圖已成功發布並通過 CloudFront 雜湊驗證；S3 原始網址無法匿名讀取。

一般 IAM user 金鑰不需要 `AWS_SESSION_TOKEN`；臨時憑證須提供 session token。也可透過 AWS CLI 的既有 profile 並在 `.env` 指定 `AWS_PROFILE`。沒有有效的預設 profile 時，程式不會自行選取其他 profile。部署 EC2 後使用 instance role，移除本地 IAM 金鑰設定。

## AWS 設定需求

- S3 保持私有並開啟 Block Public Access，不使用 public-read ACL。
- CloudFront S3 origin 指向這個 Bucket，Origin path 留空，使用 OAC 與 HTTPS。
- CloudFront 的商品圖片路徑需允許訪客 GET/HEAD，不需會員登入或 viewer 簽名 URL。
- Bucket policy 的 CloudFront 讀取權限限制於這個 distribution 的 `catalog/*`。未來會員原圖／生成圖不可沿用公開商品路徑或公開 CloudFront behavior。
- 執行上傳的 IAM 身分需要 `s3:PutObject`、`s3:GetObject`，資源為 `arn:aws:s3:::kinu-tabi-app-images-2026/catalog/*`。程式不要求列舉整個 Bucket、刪除物件或修改 AWS 權限。若 Bucket 使用 SSE-KMS，還需對應 KMS 與 OAC 解密權限。
- 一般 `<img>` 跨來源顯示不需要開放 S3 CORS；未來本人照片直傳的 CORS 另行設計。

程式不會修改 Bucket policy、CloudFront 設定或 IAM 權限。相關設定依 AWS 官方 [OAC 文件](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html)。

## 發布

在 backend 執行：

```powershell
uv pip install --python .venv/Scripts/python.exe -r requirements-dev.txt
.venv/Scripts/python.exe manage.py migrate
.venv/Scripts/python.exe manage.py publish-catalog
```

流程：

1. 只讀取有上架方案、商品與門市關聯的 `product_assets`，檢查來源為 `catalog-media` 中的 WebP。
2. 上傳至 `catalog/{圖片UUID}/{內容SHA256}.webp`，設定正確 MIME 與一年 immutable cache。無 ACL，不覆寫既有物件；重跑會檢查既有物件資訊並驗證內容。
3. 確認 S3 原始網址無法匿名讀取，且 CloudFront 回 200、WebP MIME 與相同內容雜湊。
4. 全部成功後，才以同一個資料庫交易寫入 `s3_key`。若失敗，資料庫維持原來源；已成功上傳的商品物件保留，重跑會沿用。修正 CloudFront 後可能需要等待錯誤快取到期再重跑。

重新啟動 FastAPI 並開啟商品目錄。已發布圖片的 `images[].url` 直接為 HTTPS CloudFront 網址；未發布圖片保留本地 API 網址。前端沿用既有圖片欄位與 lazy loading。舊 `/api/catalog-assets/{UUID}` 會先檢查上架狀態，再回 302 至 CloudFront。

原始 PNG、本地 WebP 與預設模特兒來源照片都保留。這個指令不會掃描整個 assets 資料夾，也不會上傳模特兒、會員原圖或生成圖。

商品下架後，API 不再提供該圖片連結，舊 API 圖片入口回 404；已知的 CloudFront 商品網址及瀏覽器快取仍可存取。公開商品圖不提供即時撤回保證；如需移除既有 CDN 圖片，另安排刪除物件與 CloudFront invalidation。私人照片必須使用獨立的授權與短效網址流程。

## 回復本地來源

`image_key` 與本地 WebP 仍在。對需要回復的 `product_assets` 將 `s3_key` 設為 NULL 即回復本地 API；這不會刪除 S3 物件。這項資料變更應在需要回復時明確執行，發布失敗時不必手動回復。

## 驗證

```powershell
$env:RUN_DATABASE_TESTS='1'
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

單元測試使用模擬 S3，驗證禁止覆寫、存取失敗、私有路徑拒絕與圖片入口切換。真實 S3／CloudFront 內容驗證由 `publish-catalog` 執行；未成功執行這個指令前，不能視為 AWS 已串接完成。
