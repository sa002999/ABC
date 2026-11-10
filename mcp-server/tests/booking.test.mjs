import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createBooking, confirmBooking, prepareBooking } from '../booking.mjs';

const draftId = '30000000-0000-4000-8000-000000000001';
const quoteToken = '30000000-0000-4000-8000-000000000002';
const holdId = '30000000-0000-4000-8000-000000000003';
const time = '2026-11-10T09:00:00+09:00';

test('member booking uses server authorization and website-origin handoff', async ({ mock }) => {
  const config = { apiOrigin: 'https://api.example.test', webOrigin: 'https://web.example.test' };
  const selection = { storeId: draftId, slotId: holdId, guests: [{ guestType: 'ADULT_FEMALE', planId: draftId, kimonoId: holdId }] };
  await assert.rejects(createBooking(config).prepare(selection), { code: 'MCP_TOKEN_REQUIRED' });
  assert.equal(prepareBooking.safeParse({ ...selection, userId: draftId }).success, false);
  assert.equal(confirmBooking.safeParse({ draftId, quoteToken, confirmed: false }).success, false);

  const auth = 'Bearer local-test-only';
  const calls = mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(options.headers.Authorization, auth);
    if (url.pathname.endsWith('/prepare')) {
      assert.deepEqual(JSON.parse(options.body), selection);
      return Response.json({ draftId, quoteToken, serverTime: time, startsAt: time, expiresAt: time,
        storeName: { 'zh-Hant': 'Store' }, total: 1500, isDemo: true, paymentAvailable: true,
        lineItems: [{ name: 'Plan', total: 1500 }], contactEmail: 'private@example.test' });
    }
    assert.equal(url.href, 'https://api.example.test/api/mcp/booking/hold');
    return Response.json({ draftId, holdId, status: 'HELD', expiresAt: time, serverTime: time, total: 1500 });
  });
  const booking = createBooking({ ...config, memberAuthorization: auth });
  const quote = await booking.prepare(selection);
  assert.equal(quote.view, 'bookingQuote');
  assert.equal(quote.storeName, 'Store');
  assert.equal(quote.contactEmail, undefined);
  const hold = await booking.hold({ draftId, quoteToken, confirmed: true });
  assert.equal(hold.paymentUrl, `https://web.example.test/booking?draftId=${draftId}&holdId=${holdId}`);
  assert.equal(calls.mock.callCount(), 2);
});
