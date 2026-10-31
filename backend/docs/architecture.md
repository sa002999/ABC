# 後端架構

採用依功能分組的模組化單體（modular monolith），搭配薄 router 與功能內分層。FastAPI 沒有強制目錄標準；這種結構適合目前規模，未引入 repository 抽象、ORM 或依賴注入框架。
React 負責畫面；FastAPI 負責 HTTP API、權限、商業規則與外部服務。

```text
backend/
├── app/
│   ├── main.py                 # 建立應用、註冊 router 與生命週期
│   ├── core/                   # 設定、連線池、錯誤、middleware、React 預覽
│   ├── integrations/           # Firebase、S3、Vertex SDK 邊界
│   └── modules/
│       ├── accounts/           # 身分驗證與會員同步
│       ├── stores/             # 門市
│       ├── catalog/            # 商品、方案、共用穿搭規則
│       ├── looks/              # 收藏造型
│       ├── bookings/           # 草稿、報價、名額與庫存暫留
│       └── try_on/             # 人物來源、照片、生成任務與 worker
├── commands/
│   ├── migrate.py
│   ├── seeds/                  # 明確執行的測試資料初始化
│   └── maintenance/            # 儲存檢查、發布、診斷
├── migrations/                # 既有 SQL 與版本名稱保持原樣
├── tests/                     # 單元與整合測試
├── data/                      # 商品來源、預覽圖與部署資源
│   └── ml-models/             # MediaPipe 等機器學習模型檔
├── var/                       # 不進 Git 的執行產物、驗證紀錄
├── docs/
├── manage.py                  # 保留既有 CLI 命令
└── .env                       # 本地秘密，不進 Git
```

## 模組內責任

- `router.py`：HTTP 路徑、輸入與輸出模型、認證及資料庫依賴，呼叫服務或查詢。
- `schemas.py`：Pydantic 契約與輸入驗證。
- `service.py`：使用案例、寫入與交易流程。
- `queries.py`：讀取 SQL 或服務需要的資料存取。
- `rules.py`：價格、配件與庫存時段等規則。

僅建立實際需要的檔案。`try_on/photos.py` 管理照片流程，`try_on/pose_check.py` 管理人物與姿勢檢查，`try_on/worker.py` 管理背景生成與清理；`catalog/media.py` 管理本地商品圖讀取。姿勢檢查模型位於 `data/ml-models/pose_landmarker_lite.task`，與人物照片及預覽圖分開存放。

## 依賴與交易

`main → router → service/queries/rules → core/integrations`。模組不匯入其他模組的 router。
收藏、預約及試穿沿用 catalog 的穿搭 schema 與驗證，避免各自定義腰帶、套餐規則。
資料庫仍使用 psycopg 與既有連線池；原有鎖、交易、冪等性及回滾邊界保留。外部 AI 呼叫不放進資料庫交易。

前端與後端分離不會禁止 MVC；此專案選擇這種分層方式，是為了讓 API、商業規則與外部服務的責任更清楚。

所有資料路徑以 `core/config.py` 定位 backend；不依賴 shell 當前目錄。模組匯入不執行 migration 或 seed。
