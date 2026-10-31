# 維護與資料初始化

從 backend 執行 `.venv/Scripts/python.exe manage.py <command>`。CLI 名稱保持不變，可用 `--help` 查看全部命令。

| 命令 | 用途 |
|---|---|
| check | 檢查資料庫連線 |
| migrate | 套用尚未執行的 migrations，沿用 schema_migrations |
| seed-demo | 初始化示範門市 |
| seed-catalog | 初始化示範商品與方案 |
| seed-booking-demo | 初始化預約測試所需時段、實體庫存與設定 |
| seed-models | 初始化預設模特兒與預覽 |
| publish-catalog | 發布和服／腰帶商品圖、方案封面及門市照片到 S3，驗證 CloudFront 後更新資料庫 |
| check-react | 檢查 Firebase 專案與上傳 CORS |
| configure-react-cors | 修改 S3 CORS；執行前確認目標 bucket |
| check-photo-storage | 檢查私人照片儲存與 CORS |
| try-on-worker | 執行背景試穿工作與既有清理流程 |
| cleanup-photo-uploads | 清理逾期上傳 |
| cleanup-generations | 清理逾期生成圖 |
| cleanup-booking-holds | 釋放逾期暫留，保留待付款保護 |

既有環境整理資料夾時不需要重新 migration 或 seed。seed 是開發資料初始化，並非正式訂單或付款。
`data/assets` 存原始圖；`data/catalog-media` 與 `data/model-previews` 保存既有生成預覽。
本地診斷可執行 `.venv/Scripts/python.exe -m commands.maintenance.measure_db`。
秘密與憑證沿用 `.env` 和原有外部位置，不移入 data 或 Git。

## 商品圖片與系列（2026-10-23）

女性和服為 RKH0002、RKH0057、RKH0103；男性和服為 RKM0001～RKM0003；女性腰帶為 ROW0001～ROW0003。
原圖位於 `data/assets/kimono` 與 `data/assets/obi`，共九張；`obi-RKH0103.png` 已移除。
依序執行 `migrate`、`seed-catalog`、`publish-catalog`，會建立本地 WebP、商品關聯並驗證 S3／CloudFront。
`plan_kimonos` 記錄方案可選的和服，新增款式不會建立額外的收費方案。
腰帶沿用既有前兩筆 ID 與價格；第三款沿用第二款示範價格。男性款式於示範門市各初始化三件示範庫存，既有庫存不覆寫。
前端方案詳情、試穿、預約及收藏編輯共用挑選元件，選定和服或腰帶後顯示該商品圖片。

## 腰帶試穿與既有圖片重用

- `data/assets/kimono-obi/` 保存九張完整女性和服＋新腰帶 PNG，檔名為 `RKH0002_ROW0001.png` 等三乘三組合。原先 RKW 開頭的九張檔案已依相同數字改為 RKH。
- 合成圖只供 AI 使用，不加入公開商品圖、不上傳至公開 CloudFront；部署 API 與 worker 時需包含此目錄。
- `POST /api/try-on/sessions/{sessionId}/generations` 接受選填 `beltId`。未選腰帶使用原商品圖；選腰帶使用完整合成圖。送至 Vertex 的衣物輸入永遠只有一張完整和服圖。
- 合成素材缺少或無法讀取時回 `422 OUTFIT_IMAGE_UNAVAILABLE`，不建立任務、不扣額度、不改用其他圖片。
- 同一會員、同一人物照片或模特兒版本、同款和服／腰帶、同一衣物素材版本，優先重用成功且未刪除、未過期的網站結果。方案不同不影響圖片重用。
- 重用回 HTTP 200、`reused: true` 與原任務 ID，不呼叫 Vertex、不扣額度、不延長原本七天期限。同組合處理中則回原任務，不重複排程。
- 本人照片必須仍可使用，且目前版本的同意仍有效；撤回同意後不能透過新請求或相同 Idempotency-Key 重用。各會員隔離，失敗、過期或刪除的結果不會重用。
- 衣物版本依實際送往 Vertex 的 JPEG 內容雜湊計算；模特兒版本使用含內容雜湊的 source_key。更換來源或素材會形成新組合。舊任務若未記錄來源／衣物版本，不推定為可重用。
- 不提供強制重新生成的選項。前端顯示成功結果後停用該搭配的試穿按鈕，更換人物、和服或腰帶後才重新查詢。
- 生成紀錄回傳 `beltId`；收藏、預約及我的生成圖沿用完整搭配，拒絕將不同腰帶的結果附加到目前搭配。

更新後執行 `migrate`，並重啟 API 與 `try-on-worker`。本機前端由 FastAPI 提供時需重新 `npm run build`。

## 會員人物照片庫與男女模特兒（2026-10-23）

- 每會員最多三張有效人物原圖，可包含已取得當事人同意的同行者；照片與試穿工作階段分開呈現。`GET /api/try-on/photos` 列照片，`DELETE /api/try-on/photos/{photoId}` 刪指定照片。
- 新增或指定替換共用既有上傳／驗證流程；上傳 ticket 的 `replacePhotoId` 指向目標原圖。成功才替換，格式驗證／傳輸失敗保留舊圖；更新會讓舊照片在各工作階段的來源參照失效，但不刪既有生成圖或收藏。
- 同會員的新增、替換、刪除與驗證使用會員交易鎖。有效新圖與未到期的新圖 ticket 共用三個名額；替換 ticket 不額外佔名額，不允許不同分頁繞過上限。
- 使用照片庫原圖建立新試穿階段時傳 `source: SELF, photoId`，沿用該原圖的有效同意；生成圖 ID 不會被當成照片 ID。新增／替換使用新版同意 `photo-consent-2026-10-23`，舊原圖既有的 10/17 同意仍可供該圖使用。
- `014_member_photo_library.sql` 將舊帳號有效原圖保留最新三張，其餘標記待清除；過渡期上傳 ticket 過期。套用後執行 `cleanup-photo-uploads` 清除私有原圖物件，生成圖與收藏保留。
- 模特兒原圖 `data/assets/default models/person-1.jpg`～`person-3.jpg` 為女生，`person-4.jpg`～`person-6.jpg` 為男生。`seed-models` 建立各三位帶 role 的資料、公開本地預覽及私人 S3 來源圖。
- 試穿頁先選人物照片或商店模特兒；照片庫逐張選用、替換、刪除，未滿可新增。模特兒依旅客角色自動預選第一位並顯示預覽；和服／腰帶商品預覽維持獨立。
- 更新後重啟 worker，避免舊程序仍只驗證人物照片的原始上傳工作階段。


## 探索方案與封面

探索方案使用 migration `015_experience_plans.sql`：單人 1 人 NT$1,500、情侶固定一男一女 2 人 NT$2,800、團體 2～3 人且每人 NT$1,400。舊方案僅下架，既有紀錄保留。`seed-catalog` 會維持這三種方案，不重新上架舊方案。

`publish-catalog` 會將仍指向 `/assets/` 的上架方案封面從 `frontend/public/assets` 讀取 WebP，發布到既有 `catalog/{方案 UUID}/{SHA256}.webp`，驗證成功後更新 `plans.cover_image_url` 為 CloudFront 網址。已切換的封面不重複發布；本地檔案保留作為開發素材與回復來源。執行初次封面發布的環境需保留 frontend/public/assets。

## 公開門市照片與圖片發布（2026-10-24）

先執行 `manage.py migrate`，套用 `017_store_images.sql`，再執行 `manage.py publish-catalog`。
門市照片來源為 `data/assets/store/kyoto.jpg`（demo-kyoto）與 `data/assets/store/tokiyo.jpg`（demo-tokyo，沿用來源檔名）。發布時轉為最長邊 1600px 的 WebP，物件鍵沿用 `catalog/{門市 UUID}/{SHA256}.webp`，不需擴大既有公開路徑權限。僅填入這兩間上架示範門市尚未設定的 `image_url`；既有門市圖片不覆寫。

所有本批圖片均完成 S3 原始網址不可匿名讀取、CloudFront HTTP 200、WebP MIME 與 SHA256 一致的檢查後，才在同一個資料庫交易更新圖片引用。失敗可重跑，原始來源檔保留。
門市 API 的列表與詳情新增 `imageUrl`；前端城市入口、展開門市資訊及門市詳情使用此網址。重新啟動後端以載入欄位與發布邏輯；使用 FastAPI 靜態前端時需重新 `npm run build`。

目前來源共 3 張方案封面、6 張和服商品圖、3 張腰帶圖與 2 張門市照片。和服 API 與發布流程保留 `product_assets` 多圖與排序支援，目前每款只有一張來源；新增角度圖需先建立對應商品圖片資料，不能以和服＋腰帶 AI 合成素材代替。


## 場景生成

執行 `manage.py migrate` 套用 `016_scene_generations.sql`，重新建置前端並重啟 API／`try-on-worker`。場景沿用 Google ADC、GOOGLE_CLOUD_PROJECT、私有 S3 與現有任務工作程序；預設 `VERTEX_SCENE_MODEL=gemini-nano-banana-2.1`、`VERTEX_SCENE_LOCATION=global`，不會改動 Virtual Try-On 地區。

試穿與場景共用每日 5 次額度。場景只接受本人的有效 TRY_ON 結果，不接受 SCENE 作來源；重用有效結果不扣次。背景程序會在 Google 呼叫前重驗人物同意與原始結果。失敗不自動重送，仍保留原始試穿圖，使用者重新確認時只重試場景一步。提示詞版本與模型名稱納入重用指紋；任務保存提示快照。場景圖保留 7 天，透過短效簽名網址提供；不要在日誌記錄圖片或供應商完整錯誤。

驗證：`RUN_DATABASE_TESTS=1 python -m unittest tests.test_scenes`（回滾交易、Google／S3 測試替身，不會產生付費影像）。真實畫質仍須在會員明確確認後測試。

## 新上傳人物照片的姿勢檢查（2026-10-24）

- 新增／替換人物照片由既有 `/api/try-on/sessions/{sessionId}/validate` 處理：格式、大小與解析度檢查 → EXIF 方向校正與中繼資料清除 → 在記憶體執行 MediaPipe → 通過才保存正式私有來源、預覽並標記 `READY`。
- 姿勢檢查位於 `app/modules/try_on/pose_check.py`，使用本機 `data/ml-models/pose_landmarker_lite.task`：`num_poses=2`，僅接受一個偵測到的人物；雙肩、髖部、膝蓋、腳踝共 8 點的 visibility/presence 均至少 0.5，且座標落在圖片範圍內。不另外判斷正面、站立、頭部／腳尖完整、亮度或模糊；通過不保證生成畫質。
- 不合格照片標記 `REJECTED`，回傳 `NO_PERSON`、`MULTIPLE_PEOPLE` 或 `BODY_CROPPED` 與提示，不提供可用預覽、不進照片庫、不建立生成工作或扣生成額度。失敗替換保留原照片；原始暫存物件沿用清理流程。
- 模型、依賴或推論異常回 `503 PHOTO_VALIDATION_UNAVAILABLE`，不當成照片不合格、不替換原圖、不將新圖放行。上傳票證有效期間內可用相同 photoId 再次呼叫 `/validate`；逾時需重新上傳。
- 既有 `FILE_READY`／`READY` 照片、既有生成結果與預設模特兒不補驗證。舊版照片處理同意仍可使用原照片；新增／替換需同意新版 `photo-consent-2026-10-24-pose`，說明後端 MediaPipe 檢查。
- 不需新增資料庫 migration。更新後重新啟動 API 與 `try-on-worker`，讓兩者讀取相同的同意版本；前端執行 `npm run build`。完整部署需包含 `app/modules/try_on/pose_check.py`、`data/ml-models/pose_landmarker_lite.task` 與 requirements.txt 指定的 MediaPipe。

驗證：`python -m unittest tests.test_pose_check` 包含實際 Lite 模型的空白圖與現有模特兒照檢查；`RUN_DATABASE_TESTS=1 python -m unittest tests.test_person_sources` 使用 RDS 回滾交易、S3／姿勢檢查替身測試拒絕、替換、重試與舊圖相容，不呼叫付費生成服務。Windows 沙箱可能阻止 TestClient 或暫存檔，這類測試可在一般終端執行。
