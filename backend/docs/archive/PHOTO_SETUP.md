> 歷史功能設定參考：目前啟動、路徑與操作請見 [現行文件索引](../README.md)。

# 本人照片上傳：需要先完成的 AWS 設定

2026-10-17：使用者已完成下列設定，重新驗證 S3 與 CloudFront 均拒絕匿名讀取私人路徑，本地直傳 CORS 通過。以下保留設定步驟供部署時參考。檢查只使用無個資測試物件並於完成後清除。

## 1. 限制 CloudFront 的 Bucket policy

AWS Console → S3 → `kinu-tabi-app-images-2026` → Permissions → Bucket policy。

找到 Principal 為 `cloudfront.amazonaws.com` 的 Allow statement。保留原有 Principal、Action、Condition（尤其 distribution ARN），把該 statement 的 Resource 從整個 Bucket 的 `/*`，改成公開商品圖片範圍：

```json
"Resource": "arn:aws:s3:::kinu-tabi-app-images-2026/catalog/*"
```

其他既有 statement 保留；不要把整份 Bucket policy 換成上面這一行。如果還有其他 CloudFront Allow statement，也要確認沒有允許 `private/*`。Block Public Access 保持開啟。

## 2. 設定直傳 CORS

同一 Bucket → Permissions → Cross-origin resource sharing (CORS)，加入以下規則。若已有 CORS，保留仍需使用的規則，合併這一筆；若你的本地服務使用其他埠，也加入相符的 Origin。

```json
[
  {
    "AllowedOrigins": [
      "http://localhost:8000",
      "http://127.0.0.1:8000",
      "http://localhost:8010",
      "http://127.0.0.1:8010"
    ],
    "AllowedMethods": ["POST", "GET", "HEAD"],
    "AllowedHeaders": ["content-type"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 300
  }
]
```

之後部署 Vercel 時，加入正式前端網域。CORS 不代表 S3 存取授權；上傳與私人預覽仍須短效簽名。

## 3. 後端 IAM 權限

目前 profile 已實測可在 `private/try-on/*` 讀取、寫入與刪除。維持 `s3:PutObject`、`s3:GetObject`、`s3:DeleteObject`；不需要把 Bucket 或會員照片設為公開。若開啟 S3 版本控制，另需私人資料刪除規劃，不能把建立 delete marker 當成舊版本已清除。

設定完成後回覆「已完成 AWS 照片設定」，我會重新檢查私人路徑與瀏覽器直傳。程式也會檢查私人路徑，發現 CloudFront 可匿名讀取時拒絕提供上傳網址。

不需要下載姿態檢查模型；格式、尺寸與 EXIF 處理在本機執行。單人／完整度／光線等語意品質檢查依使用者決定延後，通過檔案檢查不代表人物品質已通過。AI 生成整合與驗收狀態見 [TRY_ON.md](TRY_ON.md)。

## 4. 初始化與維護

在 backend 目錄執行（本次已完成 migration 與三張模特兒匯入）：

```powershell
.venv/Scripts/python.exe manage.py migrate
.venv/Scripts/python.exe manage.py check-photo-storage
.venv/Scripts/python.exe manage.py seed-models
```

模特兒原圖經方向校正、移除 EXIF 後存於私人 S3 路徑；公開介面僅提供縮圖。第三張照片有狗遮擋腿部，介面會提醒可能影響試穿。

會員登入後進入 `/#/try-on`，選擇方案與人物來源。本人照片須明確同意後才能選取，流程為取得短效簽名→瀏覽器直傳 S3→後端驗證實際圖片→保存私人來源。格式支援 JPEG、PNG、HEIC，最多 10 MiB，長邊 1200～6000 像素。照片檔名不寫入資料庫；私人原圖不提供下載網址，縮圖網址有效 120 秒。

照片通過檔案檢查後標為 `FILE_READY`、`qualityStatus=PENDING`；這不代表人物品質合格。後續生成流程允許此檔案來源，但須另行確認生成，畫面會揭露人物品質尚未檢查。

替換成功才清除舊來源；驗證失敗會保留舊照片與搭配。可刪除原圖、撤回本工作階段同意、跨裝置載入來源並更換和服搭配。刪除先立即停止使用，再清除儲存物件，失敗會保留重試旗標。原圖、生成圖與收藏分開管理；帳號刪除流程尚未實作，後續須接入相同清除機制。

清除失敗、逾時上傳及簽名有效期內重傳的暫存物件，可重跑：

```powershell
.venv/Scripts/python.exe manage.py cleanup-photo-uploads
```

每次最多處理 100 筆，可重複執行。EC2 上線前須排程定期執行，並建議加上僅針對 `private/try-on/uploads/` 的 S3 一日暫存清理規則；永久來源不設定固定期限。若啟用版本控制，清除還需要 `s3:ListBucketVersions` 與 `s3:DeleteObjectVersion` 權限，以真正清除所有版本。

## 5. 驗證

```powershell
$env:RUN_DATABASE_TESTS='1'
.venv/Scripts/python.exe -m unittest tests.test_person_sources -v
```

加設 `RUN_PHOTO_STORAGE_TESTS=1` 可執行真實 S3 直傳與私人預覽測試。只使用人工建立的白色測試圖，完成後刪除測試物件，資料庫交易會回滾；不呼叫 Vertex AI。
