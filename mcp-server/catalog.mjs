import { z } from 'zod';

export const filtersSchema = z.object({
  city: z.enum(['KYOTO', 'TOKYO']).describe('旅客要前往的城市。'),
  partySize: z.number().int().min(1).max(3).describe('整團成人總人數，非單一方案人數。'),
  keyword: z.string().max(100).default(''),
  page: z.number().int().min(0).max(100000).default(0),
  pageSize: z.number().int().min(1).max(12).default(6),
  sort: z.enum(['recommended', 'priceAsc', 'priceDesc']).default('recommended'),
}).strict();
export const detailSchema = z.object({ planId: z.string().uuid() }).strict();
const localized = z.union([z.string(), z.record(z.string(), z.string())]);
const planSchema = z.object({
  id: z.string().uuid(), name: localized, summary: localized, description: localized,
  kind: z.enum(['SINGLE', 'COUPLE', 'GROUP']), basePrice: z.number().int().nonnegative(),
  currency: z.literal('TWD'), durationMinutes: z.number().int().positive(),
  includedItems: z.array(z.string()), isDemo: z.boolean(), coverImageUrl: z.string().nullable().optional(),
  stores: z.array(z.object({ id: z.string().uuid(), city: z.enum(['KYOTO', 'TOKYO']), name: localized })).min(1),
  kimono: z.object({ images: z.array(z.object({ url: z.string(), kind: z.string() })).default([]) }),
});
const listSchema = z.object({ data: z.array(planSchema), total: z.number().int().nonnegative(), nextPage: z.number().int().nonnegative().nullable() });
export const text = value => typeof value === 'string' ? value :
  value['zh-Hant'] || value['zh-TW'] || value.en || Object.values(value)[0] || '';

export class CatalogError extends Error {
  constructor(code, message) { super(message); this.code = code; }
}

export function createCatalog(config) {
  async function request(path, schema, options = {}) {
    let response;
    try {
      response = await fetch(new URL(path, config.apiOrigin), { signal: AbortSignal.timeout(10000), redirect: 'error', ...options, headers: { Accept: 'application/json', ...options.headers } });
    } catch {
      throw new CatalogError('CATALOG_UNREACHABLE', '目前無法連線商品服務，請稍後重試。');
    }
    if (!response.ok && [401, 403, 409, 422].includes(response.status)) {
      const payload = await response.json().catch(() => ({}));
      throw new CatalogError(payload.error?.code || 'INVALID_SELECTION', payload.error?.message || '請確認會員授權與搭配條件。');
    }
    if (!response.ok) throw new CatalogError(response.status === 404 ? 'PLAN_NOT_FOUND' : 'CATALOG_UNAVAILABLE',
      response.status === 404 ? '找不到方案，可能已下架。請重新查詢。' : '商品服務暫時無法提供資料，請稍後重試。');
    try { return schema.parse(await response.json()); }
    catch { throw new CatalogError('INVALID_CATALOG_RESPONSE', '商品資料格式不完整，暫時無法顯示。'); }
  }
  function imageUrl(raw) {
    if (!raw) return null;
    try {
      const url = new URL(raw, raw.startsWith('/assets/') ? config.assetOrigin : config.apiOrigin);
      if (!url.username && !url.password && config.imageOrigins.includes(url.origin)) return url.href;
    } catch { /* Invalid upstream image is omitted, not fetched by the MCP service. */ }
    return null;
  }
  function adapt(plan) {
    return {
      id: plan.id, name: text(plan.name), summary: text(plan.summary), description: text(plan.description),
      kind: plan.kind, basePrice: plan.basePrice, currency: plan.currency,
      priceUnit: plan.kind === 'COUPLE' ? '／兩人一組' : '／人',
      participationRule: { SINGLE: '此方案供一位成人使用；多人可逐位搭配適用方案。', COUPLE: '此方案限一位女生與一位男生，共兩人。', GROUP: '此方案限兩至三位成人，每人計價。' }[plan.kind],
      durationMinutes: plan.durationMinutes, includedItems: plan.includedItems, isDemo: plan.isDemo,
      imageUrl: imageUrl(plan.coverImageUrl) || imageUrl(plan.kimono.images.find(a => a.kind === 'PRODUCT')?.url),
      stores: plan.stores.map(s => ({ id: s.id, city: s.city, name: text(s.name) })),
    };
  }
  return {
    async availability(input) {
      const body = availabilitySchema.parse(input);
      const data = await request('/api/catalog/party-availability', availabilityResultSchema, { method: 'POST', signal: AbortSignal.timeout(55000), headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      return { ...data, store: { ...data.store, name: text(data.store.name) } };
    },
    async kimonos(input) {
      const filters = kimonoFiltersSchema.parse(input);
      const query = new URLSearchParams({ city: filters.city, plan: filters.planId, page: String(filters.page), pageSize: '12' });
      const data = await request(`/api/kimonos?${query}`, z.object({ data: z.array(kimonoSchema), nextPage: z.number().int().nullable() }));
      return { view: 'kimonos', filters, kimonos: data.data.map(k => ({ ...k, name: text(k.name), imageUrl: imageUrl(k.images.find(a => a.kind === 'PRODUCT')?.url), images: undefined })), nextPage: data.nextPage,
        notice: '請為每位旅客選擇適用款式，完成後檢查全員搭配。尚未查詢日期庫存。' };
    },
    async kimono(input) {
      const { kimonoId } = kimonoDetailSchema.parse(input);
      const k = await request(`/api/kimonos/${kimonoId}`, kimonoSchema);
      return { view: 'kimono', kimono: { ...k, name: text(k.name), imageUrl: imageUrl(k.images.find(a => a.kind === 'PRODUCT')?.url), images: undefined }, notice: '商品資訊不代表可預約或庫存保留。' };
    },
    async summary(input) {
      const body = outfitSchema.parse(input);
      const data = await request('/api/catalog/outfit-summary', summarySchema, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      return { ...data, commonStores: data.commonStores.map(s => ({ ...s, name: text(s.name) })) };
    },
    async member() {
      if (!config.memberAuthorization) throw new CatalogError('MCP_TOKEN_REQUIRED', '請在 AI 客戶端的 MCP 連線設定填入本人 Bearer token，勿貼入對話。');
      const data = await request('/api/mcp/member', z.object({ authenticated: z.literal(true), channel: z.literal('MCP') }), { headers: { Authorization: config.memberAuthorization } });
      return { view: 'member', ...data, notice: '會員連線驗證成功；不代表照片處理、生成或建立草稿的授權。' };
    },
    async list(input) {
      const filters = filtersSchema.parse(input);
      const query = new URLSearchParams({ city: filters.city, keyword: filters.keyword, page: String(filters.page), pageSize: String(filters.pageSize), sort: filters.sort });
      const data = await request(`/api/plans?${query}`, listSchema);
      return { view: 'plans', filters, plans: data.data.map(adapt), total: data.total, nextPage: data.nextPage,
        availabilityChecked: false, notice: '目前僅探索方案。整團人數不代表每個方案皆適用；價格為方案基礎價，非整筆報價。尚未檢查日期、名額與庫存，也未建立預約。' };
    },
    async detail(input) {
      const { planId } = detailSchema.parse(input);
      return { view: 'plan', plan: adapt(await request(`/api/plans/${planId}`, planSchema)), availabilityChecked: false,
        notice: '此操作只選定方案，尚未挑選全員和服或建立預約；不保留名額與庫存。' };
    },
  };
}

export const kimonoFiltersSchema = z.object({ city: z.enum(['KYOTO', 'TOKYO']), planId: z.string().uuid(), page: z.number().int().min(0).max(100000).default(0) }).strict();
export const kimonoDetailSchema = z.object({ kimonoId: z.string().uuid() }).strict();
export const outfitSchema = z.object({ city: z.enum(['KYOTO', 'TOKYO']), guests: z.array(z.object({ guestType: z.enum(['ADULT_FEMALE', 'ADULT_MALE']), planId: z.string().uuid(), kimonoId: z.string().uuid() }).strict()).min(1).max(3) }).strict();
export const availabilitySchema = outfitSchema.extend({ storeId: z.string().uuid(), from: z.iso.date(), to: z.iso.date() }).strict();
const availabilityResultSchema = z.object({
  view: z.literal('partyAvailability'), ...availabilitySchema.shape,
  store: z.object({ id: z.string().uuid(), name: localized }),
  slots: z.array(z.object({ slotId: z.string().uuid(), startsAt: z.iso.datetime({offset:true}), endsAt: z.iso.datetime({offset:true}),
    remaining: z.number().int().nonnegative(), available: z.boolean(), reason: z.string().nullable(), inventoryChecked: z.boolean(),
    isDemo: z.boolean(), rentalEndsAt: z.array(z.iso.datetime({offset:true})).min(1).max(3) })),
  timezone: z.literal('Asia/Tokyo'), serverTime: z.iso.datetime({offset:true}), availabilityChecked: z.literal(true),
  inventoryReserved: z.literal(false), bookingCreated: z.literal(false), isDemo: z.boolean(), notice: z.string(),
});
const kimonoSchema = z.object({ id: z.string().uuid(), sku: z.string(), name: localized, gender: z.enum(['FEMALE', 'MALE']), kimonoType: z.string(), styleTags: z.array(z.string()), isDemo: z.boolean(), images: z.array(z.object({ url: z.string(), kind: z.string() })) });
const summarySchema = z.object({ view: z.literal('outfitSummary'), city: z.enum(['KYOTO', 'TOKYO']), guests: outfitSchema.shape.guests,
  lineItems: z.array(z.object({ guestIndex: z.number().int(), name: localized, label: z.string(), total: z.number().int().nonnegative() }).passthrough()),
  estimatedTotal: z.number().int().nonnegative(), currency: z.literal('TWD'), commonStores: z.array(z.object({ id: z.string().uuid(), name: localized, city: z.enum(['KYOTO','TOKYO']) })),
  isDemo: z.boolean(), availabilityChecked: z.literal(false), bookingCreated: z.literal(false), notice: z.string() });
