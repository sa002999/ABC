import { z } from 'zod';
import { CatalogError, outfitSchema, text } from './catalog.mjs';

const id = z.uuid();
const timestamp = z.iso.datetime({ offset: true });
const amount = z.number().int().nonnegative();
const localized = z.union([z.string(), z.record(z.string(), z.string())]);
export const prepareBooking = z.object({
  storeId: id, slotId: id, guests: outfitSchema.shape.guests,
  replaceDraftId: id.optional(), replaceVersion: z.number().int().positive().optional(),
}).strict();
export const confirmBooking = z.object({ draftId: id, quoteToken: id, confirmed: z.literal(true) }).strict();

const quote = z.object({
  draftId: id, quoteToken: id, expiresAt: timestamp, serverTime: timestamp,
  storeName: localized, startsAt: timestamp, total: amount, isDemo: z.boolean(), paymentAvailable: z.boolean(),
  lineItems: z.array(z.object({ name: localized, total: amount })),
});
const conflict = z.object({ draftConflict: z.literal(true), draftId: id, version: z.number().int().positive() });
const hold = z.object({
  draftId: id, holdId: id, status: z.string(), expiresAt: timestamp, serverTime: timestamp, total: amount,
});

export function createBooking(config) {
  const website = path => new URL(path, config.webOrigin).href;
  async function request(action, schema, body) {
    if (!config.memberAuthorization) {
      throw new CatalogError('MCP_TOKEN_REQUIRED', '請先在 MCP 連線設定使用本人會員授權。');
    }
    let response;
    try {
      response = await fetch(new URL('/api/mcp/booking/' + action, config.apiOrigin), {
        method: 'POST', redirect: 'error', signal: AbortSignal.timeout(15000),
        headers: { Authorization: config.memberAuthorization, 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    } catch {
      throw new CatalogError('BOOKING_UNREACHABLE', '目前無法連線預約服務，請重試原操作。');
    }
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      throw new CatalogError(data?.error?.code || 'BOOKING_FAILED',
        data?.error?.message || '預約服務暫時無法完成操作，請稍後重試。');
    }
    const parsed = schema.safeParse(data);
    if (!parsed.success) throw new CatalogError('INVALID_BOOKING_RESPONSE', '預約服務回應不完整，請稍後重試。');
    return parsed.data;
  }
  return {
    async prepare(body) {
      const data = await request('prepare', z.union([conflict, quote]), body);
      if (data.draftConflict) return { view: 'bookingDraftConflict', ...data, websiteUrl: website('/booking') };
      return { view: 'bookingQuote', ...data, storeName: text(data.storeName),
        lineItems: data.lineItems.map(item => ({ ...item, name: text(item.name) })),
        notice: '使用已驗證的會員聯絡資料。報價尚未保留庫存或建立正式預約。' };
    },
    async hold(body) {
      const data = await request('hold', hold, body);
      if (data.status !== 'HELD') {
        throw new CatalogError('HOLD_UNAVAILABLE', '此暫留已到期、已釋放或正在處理付款，請先至官網確認狀態。');
      }
      const params = new URLSearchParams({ draftId: data.draftId, holdId: data.holdId });
      return { view: 'bookingHold', ...data, paymentUrl: website('/booking?' + params),
        notice: '庫存已短暫保留。請使用同一會員回官網完成 Sandbox 付款。' };
    },
  };
}
