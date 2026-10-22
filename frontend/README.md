# KINU TABI React 前端

此目錄為 P_Kinu-Tabi 的現行前端，使用 React、TypeScript、Vite 與 Tailwind，串接同專案 backend 的 FastAPI。

完整啟動方式、已確認規則、示範價格、測試與 Vercel／EC2 部署準備，請閱讀 [整合說明](../INTEGRATION.md)。

```powershell
npm ci
npm run dev
```

本機網址：http://127.0.0.1:5173。API 代理目標：http://127.0.0.1:8000。AI 與到期清理須同時啟動後端 worker。

`npm test` 執行 React 商業規則與 API 測試；`npm run build` 執行 TypeScript 檢查並產生 dist。

Firebase 沿用 kinu-tabi。付款、攝影加購、腰帶 AI 穿戴與場景生成尚未開放。

`docs/step-*-progress.md`、截圖與 migration 資料為匯入專案的歷史資料，不是現行後端完成狀態；目前狀態以 ../INTEGRATION.md 為準。