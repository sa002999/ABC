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

## GitHub Actions 部署至 EC2

`development` 上的後端或 workflow 變更通過 CI 後，GitHub Actions 透過 OIDC 取得短效 AWS 憑證，對指定 EC2 發送 SSM Run Command。SSM 只部署通過 CI 且仍是遠端分支最新版本的 commit，依序安裝依賴、執行 migration、重啟 API 與試穿 worker，再檢查兩個 systemd 服務。Actions 等到 SSM 回報部署成功後，才檢查外部 HTTPS 的 `/api/health/db`。

### 建立 SSM 部署文件與 IAM 角色

1. 確認 EC2 的 SSM Agent 是 3.3.2746.0 或更新版本，以支援 `ENV_VAR` 插值。EC2 需有可讀取 GitHub `origin` 的 Git checkout、`backend/.venv`（Python 3.13）、migration 可讀取的 runtime 設定，以及 API 與 worker 的 systemd units。
2. 複製 [SSM 文件範本](../deploy/ssm-development.yml)，填入部署帳號、checkout 絕對路徑及兩個 systemd unit 名稱。以部署帳號在 EC2 的 `backend` 目錄執行 `.venv/bin/python -m pip --version`。若虛擬環境缺少 pip，先執行 `.venv/bin/python -m ensurepip`，再重新確認。部署會使用該虛擬環境的 pip 安裝依賴。更新已註冊的文件時，請將新版設為 Default version，workflow 會使用預設版本。在 EC2 所在的 AWS 帳戶和區域將其註冊為名稱 `KinuTabi-DeployBackendDevelopment` 的 Command 文件，使用 YAML 格式。文件透過 `runuser` 切換為部署帳號。該帳號需能非互動式讀取 GitHub `origin`、寫入 checkout 與 venv，並能使用 `sudo -n systemctl restart` 重啟這兩個 units。
3. 在 GitHub 建立 `backend-development` Environment，將允許部署的分支設成 `development`。在 AWS IAM 使用 GitHub OIDC provider `token.actions.githubusercontent.com`，建立以 `sts:AssumeRoleWithWebIdentity` 取得的部署角色。信任政策以 `StringEquals` 限定 `token.actions.githubusercontent.com:aud` 為 `sts.amazonaws.com`，並限定 `token.actions.githubusercontent.com:sub` 為 `repo:OWNER/REPO:environment:backend-development`，其中 `OWNER/REPO` 要換成此 workflow 所在的 GitHub repository。使用 Environment 時，OIDC subject 裡的分支限制由 GitHub Environment 的分支規則實施。
4. 在部署角色的權限政策授予下列兩項。SSM 文件由管理者註冊與更新，部署角色只需要發送命令及讀取結果。

| IAM action | Resource |
| --- | --- |
| `ssm:SendCommand` | `arn:aws:ssm:REGION:ACCOUNT_ID:document/KinuTabi-DeployBackendDevelopment` 與 `arn:aws:ec2:REGION:ACCOUNT_ID:instance/INSTANCE_ID` |
| `ssm:GetCommandInvocation` | `*`（AWS 此 action 未支援資源層級限制） |

### 設定 GitHub Environment

在 `backend-development` 設定下列 variables。這條流程的 AWS 憑證由 OIDC 核發，Run Command 透過 EC2 的 SSM Agent 送達。

| 變數 | 值 |
| --- | --- |
| `AWS_REGION` | EC2 與 SSM Command 文件所在區域 |
| `AWS_DEPLOY_ROLE_ARN` | GitHub OIDC 部署角色 ARN |
| `EC2_INSTANCE_ID` | 目標受控節點的 EC2 instance ID |
| `EC2_API_BASE_URL` | Vercel Preview 使用的後端 HTTPS 網址 |
| `EC2_DEPLOY_ENABLED` | 設為 `true` 後啟用部署 |

首次部署請在 worker 閒置時進行，因為舊程序尚未處理優雅停止。更新後，worker 收到 SIGTERM 會完成已領取的任務再退出。worker unit 的 `TimeoutStopSec` 需涵蓋完整試穿任務，包含最長 180 秒的 Vertex 請求以及前後的儲存與資料庫操作。

設定完成後，下一次符合條件的 `development` push 會觸發部署。部署失敗時，用 Actions log 裡的 command ID 在 AWS Systems Manager Run Command 查看執行紀錄。確認部署成功後，再透過 Vercel Preview 跑一次試穿。HTTPS 健康檢查涵蓋 API 與資料庫連線，完整試穿仍需驗證 worker、Vertex 和 S3。
