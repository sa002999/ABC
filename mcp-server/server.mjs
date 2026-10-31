import { readFile } from 'node:fs/promises';
import { McpServer } from '@modelcontextprotocol/server';
import { registerAppResource, registerAppTool, RESOURCE_MIME_TYPE } from '@modelcontextprotocol/ext-apps/server';
import { createCatalog, filtersSchema, detailSchema, kimonoFiltersSchema, kimonoDetailSchema, outfitSchema, availabilitySchema, CatalogError } from './catalog.mjs';
import { z } from 'zod';
import { createTryOn, tryOnOutfit, prepareTryOn, confirmTryOn, getTryOnJob, getTryOnJobs, createPhotoUpload, completePhotoUpload, tryOnMediaOrigins } from './try-on.mjs';

export const RESOURCE_URI = 'ui://kinu-tabi/plan-picker-v5.html';
export const TRY_ON_URI = 'ui://kinu-tabi/try-on-v4.html';
const annotations = { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true };

export function createServer(config) {
  const catalog = createCatalog(config);
  const tryOn = createTryOn(config);
  const server = new McpServer({ name: 'kinu-tabi', version: '0.1.0' }, {
    instructions: '先取得城市及1～3位成人總人數，再探索方案；圖片介面用 show_plan_picker。逐人選款用 list_kimonos/get_kimono_details；完整搭配用 check_outfit_summary，金額與共同門市以後端結果為準，修改後重查。全員可用時間用 check_party_availability，日期時段 UI 用 show_party_availability；先取得共同門市及日本日期，傳入完整原搭配。時段結果僅供查詢當下參考；修改搭配、門市或日期須重查，選時段不保留、不建立草稿。get_member_status 僅從 HTTP Bearer token 驗證本人；不得索取 token 貼入對話或工具參數。isDemo 必須揭露。試穿先 show_try_on 選人物，再 prepare_try_on 展示確認內容；只有本人明確確認該次人物、款式、額度與到期規則後才能 confirm_try_on。對話附圖及進度摘要不等於照片同意或生成授權。逾時用原 reviewId 重試或 get_try_on_jobs 恢復，禁止自動另建生成。傳遞 conversationId 可保留本次比較。試穿可略過，不占庫存、不代表預約或付款。',
  });
  const handle = action => async input => {
    try {
      const data = await action(input);
      const summary = data.view === 'plans'
        ? `查得 ${data.total} 個方案，本頁 ${data.plans.length} 個。\n${data.plans.map(p => `${p.name}：TWD ${p.basePrice}${p.priceUnit}${p.isDemo ? '（示範資料）' : ''}`).join('\n')}`
        : data.view === 'plan' ? `${data.plan.name}：TWD ${data.plan.basePrice}${data.plan.priceUnit}。${data.plan.description}${data.plan.isDemo ? '（示範資料）' : ''}`
        : data.view === 'kimonos' ? data.kimonos.map(k => `${k.name}（${k.gender}，${k.sku}，kimonoId=${k.id}）${k.isDemo ? ' 示範商品' : ''}`).join('\n') || '沒有符合條件的和服。'
        : data.view === 'kimono' ? `${data.kimono.name}（${data.kimono.sku}）${data.kimono.isDemo ? ' 示範商品' : ''}`
        : data.view === 'partyAvailability' ? `${data.store.name}：${data.from}～${data.to}，${data.guests.length} 位成人全員可用 ${data.slots.filter(s => s.available).length} 個時段（Asia/Tokyo）。${data.isDemo ? '示範資料。' : ''}`
        : data.view === 'outfitSummary' ? `全員估計金額 NT$${data.estimatedTotal}；共同門市：${data.commonStores.map(s => s.name).join('、') || '無'}${data.isDemo ? '（示範商品／價格）' : ''}`
        : data.view === 'tryOnSources' ? `可為「${data.kimonoName}」選擇 ${data.models.length} 位適用模特兒或 ${data.photos.length} 張本人照片；MCP 今日剩餘 ${data.usage.mcp.remaining} 次。`
        : data.view === 'tryOnReview' ? `請確認本次試穿：${data.kimonoName}／${data.source === 'MODEL' ? data.modelName : '本人照片 ' + data.photoId}。今日 MCP 剩餘 ${data.usage.mcp.remaining} 次。reviewId=${data.reviewId}，確認內容到期=${data.reviewExpiresAt}。`
        : data.view === 'tryOnJob' ? `試穿任務 ${data.jobId}：${data.status}。${data.expiresAt ? '圖片到期：' + data.expiresAt : ''}${data.failure?.message || ''}`
        : data.view === 'tryOnJobs' ? data.jobs.map(j => `${j.jobId}：${j.status}`).join('\n') || '本次尚無 MCP 試穿任務。'
        : data.view === 'photoConsent' ? '請在試穿介面閱讀照片處理說明，選擇檔案並親自勾選同意。'
        : data.view === 'photoUpload' ? '已準備本次照片的短效上傳權限，尚未確認上傳或檢查完成；不生成或扣額度。'
        : data.view === 'photoUploaded' ? `照片檢查結果：${data.photo.status}。${data.photo.issues.map(i=>i.message).join('；')} 尚未生成或扣額度。`
        : '本人 MCP 會員連線有效。';
      const { _media, _upload, ...structuredContent } = data;
      return { content: [{ type: 'text', text: `${summary}\n${data.notice || ''}` }], structuredContent,
        ...(_media || _upload ? { _meta: { ...(_media ? {media:_media} : {}), ...(_upload ? {upload:_upload} : {}) } } : {}) };
    } catch (error) {
      const known = error instanceof CatalogError;
      return { isError: true, content: [{ type: 'text', text: known ? error.message : '查詢失敗，請確認輸入後重試。' }],
        structuredContent: { error: { code: known ? error.code : 'TOOL_FAILED' } } };
    }
  };
  server.registerTool('list_plans', { title: '探索和服方案', description: '先取得城市及整團人數，再查公開方案。回傳目前價格與人數規則，不查可用性，不計算整團報價。需要 UI 可接續 show_plan_picker。', inputSchema: filtersSchema, annotations }, handle(catalog.list));
  server.registerTool('get_plan_details', { title: '查看和服方案詳情', description: '依真實方案 UUID 查目前內容與服務。UI 點選使用此工具；選擇不占名額、不建立草稿。', inputSchema: detailSchema, annotations }, handle(catalog.detail));
  server.registerTool('list_kimonos', { title: '查詢方案適用和服', description: '依城市及方案查詢適用和服，支援分頁；依 gender、styleTags 協助逐位選款。尚未檢查庫存。', inputSchema: kimonoFiltersSchema, annotations }, handle(catalog.kimonos));
  server.registerTool('get_kimono_details', { title: '查看和服詳情', description: '查詢真實和服 UUID 的公開資訊。', inputSchema: kimonoDetailSchema, annotations }, handle(catalog.kimono));
  server.registerTool('check_party_availability', { title: '查詢全員可用日期與時段', description: '先完成 check_outfit_summary，提供共同門市及全員原搭配，查詢日本日期 from/to（YYYY-MM-DD，最多31天）。後端檢查全員接待名額、不同實體和服、租借與整備時間及關店限制。限開始前24小時至未來90天；不保留庫存、不建立草稿。無可用時段時保留搭配改查其他日期，不自動換款。', inputSchema: availabilitySchema, annotations }, handle(catalog.availability));
  server.registerTool('check_outfit_summary', { title: '檢查全員搭配及共同門市', description: '提供完整 1～3 位成人搭配，由後端檢查套餐、性別與款式適用性、估計金額及共同門市。不查日期、不保留庫存、不建立草稿。', inputSchema: outfitSchema, annotations }, handle(catalog.summary));
  server.registerTool('get_member_status', { title: '驗證本人會員連線', description: '從 MCP HTTP 連線的 Bearer token 驗證本人授權。請勿把 token 或 userId 填入工具或對話。', inputSchema: z.object({}).strict(), annotations }, handle(catalog.member));
  registerAppTool(server, 'show_try_on', { title: '開啟 AI 試穿', description: '以單位旅客已選定的方案與和服開啟人物來源、生成確認及結果比較 UI；可略過。沿用 conversationId 可恢復本次任務。此工具不生成。', inputSchema: tryOnOutfit, annotations, _meta: { ui: { resourceUri: TRY_ON_URI } } }, handle(tryOn.sources));
  registerAppTool(server, 'get_photo_upload_consent', { title:'查看本人照片上傳說明',description:'只供試穿介面取得目前照片同意版本及限制，不代表使用者已同意。',inputSchema:z.object({}).strict(),annotations,_meta:{ui:{visibility:['app']}} },handle(tryOn.photoConsent));
  registerAppTool(server, 'create_photo_upload', { title:'準備本人照片上傳',description:'只供試穿介面在本人選檔、閱讀並勾選照片處理同意後使用。僅核發本次短效上傳權限，不生成、不扣額度；憑證只回傳 UI metadata。',inputSchema:createPhotoUpload,annotations:{...annotations,readOnlyHint:false,idempotentHint:false},_meta:{ui:{visibility:['app']}} },handle(tryOn.createPhotoUpload));
  registerAppTool(server, 'complete_photo_upload', { title:'檢查本人上傳照片',description:'只供試穿介面確認本次照片已上傳並執行既有格式、大小及人物驗證；重試相同 sessionId/photoId，不建立生成。',inputSchema:completePhotoUpload,annotations:{...annotations,readOnlyHint:false},_meta:{ui:{visibility:['app']}} },handle(tryOn.completePhotoUpload));
  server.registerTool('prepare_try_on', { title: '準備本次生成確認', description: '依已選定人物來源及款式建立十分鐘內有效的確認內容，尚不扣額度或呼叫 AI。SELF 只接受本人已同意且有效的照片庫 photoId。請向使用者展示確認內容、MCP 額度及到期規則。', inputSchema: prepareTryOn, annotations: { ...annotations, readOnlyHint: false, idempotentHint: false } }, handle(tryOn.prepare));
  server.registerTool('confirm_try_on', { title: '確認並生成 AI 試穿', description: '只有使用者明確確認剛才的 reviewId、人物、款式、額度及到期規則後才能呼叫。最多消耗一次 MCP 額度並啟動付費 AI。逾時以同一 reviewId 重試，禁止自動另建生成。失敗後須再次取得確認。', inputSchema: confirmTryOn, annotations: { ...annotations, readOnlyHint: false, destructiveHint: true } }, handle(tryOn.confirm));
  server.registerTool('get_try_on_job', { title: '查詢本人 MCP 試穿任務', description: '查任務進度或更新短效圖片網址，不會生成或扣額度。', inputSchema: getTryOnJob, annotations }, handle(tryOn.job));
  server.registerTool('get_try_on_jobs', { title: '恢復 MCP 試穿歷程', description: '依 conversationId 恢復本次歷程；省略時查看本人最近 MCP 任務，方便 UI 關閉後恢復。不包含網站生成圖。', inputSchema: getTryOnJobs, annotations }, handle(tryOn.jobs));
  registerAppTool(server, 'show_plan_picker', { title: '開啟方案選擇介面', description: '以已取得的城市及整團人數開啟互動方案介面，從後端重新讀取目前資料。沒有 UI 時仍回傳可讀方案結果。', inputSchema: filtersSchema, annotations,
    _meta: { ui: { resourceUri: RESOURCE_URI } } }, handle(catalog.list));
  registerAppTool(server, 'show_party_availability', { title:'開啟全員日期與時段介面', description:'以完整全員搭配、共同門市及日本日期區間開啟可用時間 UI。與 check_party_availability 相同的唯讀查詢；不保留、不建立草稿。可保留搭配修改日期或共同門市。', inputSchema:availabilitySchema, annotations,
    _meta:{ui:{resourceUri:RESOURCE_URI}} }, handle(catalog.availability));
  const ui = { prefersBorder: true, csp: { connectDomains: [], resourceDomains: config.imageOrigins } };
  // Keep existing cards readable while refreshed tool metadata advertises the current UI.
  for (const uri of [RESOURCE_URI, 'ui://kinu-tabi/plan-picker-v4.html', 'ui://kinu-tabi/plan-picker-v3.html', 'ui://kinu-tabi/plan-picker-v2.html', 'ui://kinu-tabi/plan-picker.html']) {
    registerAppResource(server, '和服方案選擇' + (uri === RESOURCE_URI ? '' : '（相容）'), uri, { mimeType: RESOURCE_MIME_TYPE, _meta: { ui } }, async () => ({
      contents: [{ uri, mimeType: RESOURCE_MIME_TYPE, text: await readFile(new URL('./dist/plan-picker.html', import.meta.url), 'utf8'), _meta: { ui } }],
    }));
  }
  for (const uri of [TRY_ON_URI, 'ui://kinu-tabi/try-on-v3.html', 'ui://kinu-tabi/try-on-v2.html', 'ui://kinu-tabi/try-on-v1.html']) {
    registerAppResource(server, 'AI 試穿與結果比較' + (uri === TRY_ON_URI ? '' : '（相容）'), uri, { mimeType: RESOURCE_MIME_TYPE, _meta: { ui } }, async () => {
      const origins = await tryOnMediaOrigins(config);
      return { contents: [{ uri, mimeType: RESOURCE_MIME_TYPE, text: await readFile(new URL('./dist/try-on.html', import.meta.url), 'utf8'),
        _meta: { ui: {prefersBorder:true,csp:{connectDomains:origins,resourceDomains:[...new Set([...config.imageOrigins,...origins])]}} } }], };
    });
  }
  return server;
}
