# 部署方向

前端：Vercel，專案根目錄 frontend，Vite build，輸出 dist。
後端：AWS EC2，部署 backend 與其 data、migrations，建立 Python 環境並安裝 requirements.txt。
人物照片驗證程式位於 `app/modules/try_on/pose_check.py`，部署需包含 `data/ml-models/pose_landmarker_lite.task`（目前提供的 Lite 模型約 5.8 MB）。模型透過 `DATA_DIR` 定位，從本機載入，不在使用者上傳時下載；缺少模型或 MediaPipe 無法執行時，新照片驗證回 503，不直接放行。既有照片與預設模特兒不補驗證。

在 backend 工作目錄執行：

```sh
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
python manage.py try-on-worker
```

API 與 worker 應由程序管理工具各自管理；正式環境不使用 --reload。EC2 前方配置 HTTPS 反向代理，秘密由執行環境提供。
設定 CORS_ORIGINS 為實際 Vercel 網域，前端 VITE_API_BASE_URL 指向後端 HTTPS 網址，並確認 Firebase authorized domains 與私人 S3 上傳 CORS。

Firebase Admin 和 Vertex AI 都透過 ADC 取得憑證。共用的 `backend/.env` 設定 `FIREBASE_PROJECT_ID` 為 Firebase 專案，`GOOGLE_CLOUD_PROJECT` 和 `GOOGLE_CLOUD_LOCATION` 為 Vertex AI 專案與試穿地區。從舊版遷移時，移除 `FIREBASE_CLIENT_EMAIL` 和 `FIREBASE_PRIVATE_KEY`。

- 本機執行 `gcloud auth application-default login` 並省略 `GOOGLE_APPLICATION_CREDENTIALS`。登入的 Google 帳號須有測試所需的 Firebase 和 Vertex AI 權限。
- EC2 共用 `kinu-tabi-ec2-role` 和既有 WIF Pool、Provider。允許這個 AWS 角色透過 `roles/iam.workloadIdentityUser` 模擬 `kinu-tabi-vertex` 和 `kinu-tabi-firebase`，並在 Firebase 專案授予後者 `firebaseauth.users.get`（例如使用 `roles/firebaseauth.viewer`）。
- 在 EC2 的兩個 systemd 服務分別設定 `Environment="GOOGLE_APPLICATION_CREDENTIALS=/實際目錄/設定檔.json"`。API 選用 `kinu-tabi-firebase-wif.json`，Worker 選用 `kinu-tabi-vertex-wif.json`。設定檔需可由各自的服務帳號讀取。更新服務設定後執行 `systemctl daemon-reload`，並在新版部署後確認登入和試穿。
部署前明確執行 migration；不在 HTTP 啟動時自動執行。不需要將開發 seed 自動帶入部署。

### 產生 Firebase WIF 設定檔

從本機 PowerShell 執行。將 `$FirebaseProjectId` 換成部署環境的 `FIREBASE_PROJECT_ID`。服務帳戶建立在已有 WIF Pool 的專案，Firebase 權限則授予在實際處理登入的專案。

```powershell
$ProjectId = 'arctic-odyssey-434811-r7'
$FirebaseProjectId = '填入 Firebase 專案 ID'
$PoolId = 'kinu-tabi-ec2'
$ProviderId = 'aws-ec2'
$AwsRoleName = 'kinu-tabi-ec2-role'
$ServiceAccountId = 'kinu-tabi-firebase'
$ServiceAccount = "$ServiceAccountId@$ProjectId.iam.gserviceaccount.com"
$ProjectNumber = (gcloud projects describe $ProjectId --format='value(projectNumber)').Trim()
$PoolPath = "projects/$ProjectNumber/locations/global/workloadIdentityPools/$PoolId"

# 若服務帳戶已建立，可略過 create。
gcloud iam service-accounts create $ServiceAccountId --project=$ProjectId

gcloud iam service-accounts add-iam-policy-binding $ServiceAccount `
  --project=$ProjectId --role='roles/iam.workloadIdentityUser' `
  --member="principalSet://iam.googleapis.com/$PoolPath/attribute.aws_role/$AwsRoleName"

gcloud projects add-iam-policy-binding $FirebaseProjectId `
  --member="serviceAccount:$ServiceAccount" --role='roles/firebaseauth.viewer'

$ConfigPath = Join-Path $env:USERPROFILE 'kinu-tabi-firebase-wif.json'
gcloud iam workload-identity-pools create-cred-config "$PoolPath/providers/$ProviderId" `
  --service-account=$ServiceAccount --aws --enable-imdsv2 --output-file=$ConfigPath
```

將產生的 JSON 複製到 EC2，讓 API 的 systemd 服務透過 `GOOGLE_APPLICATION_CREDENTIALS` 指向其絕對路徑。Worker 的服務繼續指向自己的 Vertex WIF 設定檔。在新版 API 部署後，用有效帳號登入並呼叫需要登入的 API，再確認停用帳號會被拒絕。現有的真實 Firebase 測試會建立、更新和刪除測試帳號，需要額外寫入權限。

