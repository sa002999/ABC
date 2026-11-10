import { App } from '@modelcontextprotocol/ext-apps';

const app = new App({ name: 'KINU TABI Plan Picker', version: '0.1.0' }, {});
const $ = id => document.getElementById(id);
let filters;
let nextPage = null;
let selected = null;
let busy = false;
let connected = false;
let guests = [];
let plans = [];
let outfitSummary = null;
let availability = null;
let availabilityFilters = null;
let selectedSlot = null;
let booking = null;
const garments = new Map();
const tryOnConversationId = crypto.randomUUID();

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function status(message, error = false) {
  $('status').textContent = message;
  $('status').dataset.error = String(error);
}
function controls() {
  $('search').disabled = busy || !connected;
  $('previous').disabled = busy || !connected || !filters || filters.page === 0;
  $('next').disabled = busy || !connected || nextPage === null;
  document.querySelectorAll('[data-action]').forEach(button => { button.disabled = busy || !connected || button.dataset.unavailable === 'true'; });
}
function image(plan) {
  if (!plan.imageUrl) return element('p', '商品圖片尚未提供', 'muted');
  const img = element('img');
  // Never turn API text into HTML or accept script/data URLs.
  const url = new URL(plan.imageUrl);
  if (!['http:', 'https:'].includes(url.protocol)) return element('p', '圖片暫無法顯示', 'muted');
  img.src = url.href; img.alt = plan.name; img.referrerPolicy = 'no-referrer';
  img.addEventListener('error', () => img.replaceWith(element('p', '圖片暫無法載入', 'muted')), { once: true });
  return img;
}
function price(plan) {
  return `NT$${plan.basePrice.toLocaleString('zh-TW')}${plan.priceUnit}（方案基礎價）`;
}
function resultData(result) {
  if (result.isError) throw new Error(result.content?.find(c => c.type === 'text')?.text || '查詢失敗，請重試。');
  const data = result.structuredContent;
  if (!data || !['plans', 'plan', 'kimonos', 'kimono', 'outfitSummary', 'partyAvailability', 'bookingQuote', 'bookingDraftConflict', 'bookingHold'].includes(data.view)) throw new Error('無法辨識商品回應，請重新查詢。');
  return data;
}
async function syncContext() {
  const summary = { city: filters?.city, partySize: filters?.partySize,
    selectedPlan: selected ? { id: selected.id, name: selected.name, basePrice: selected.basePrice, currency: 'TWD', priceUnit: selected.priceUnit, participationRule: selected.participationRule, isDemo: selected.isDemo } : null,
    guests: guests.map((g, i) => ({ traveler: i + 1, ...g })), outfitSummary,
    availabilityFilters, availability: availability ? { store:availability.store, serverTime:availability.serverTime,
      availableCount:availability.slots.filter(s=>s.available).length, isDemo:availability.isDemo, notice:availability.notice } : null, selectedSlot,
    availabilityChecked: availability !== null, inventoryReserved: booking?.view === 'bookingHold', bookingCreated: false };
  try {
    await app.updateModelContext({ content: [{ type: 'text', text: `KINU TABI 目前 UI 選擇：${JSON.stringify(summary)}。此為卡片狀態；只有本人操作確認按鈕才會暫留，付款完成前預約尚未成立。` }] });
    return true;
  } catch {
    status('已更新畫面，但客戶端未確認 AI 摘要同步。選定方案後可按「請 AI 介紹」明確傳送。', true);
    return false;
  }
}
function showSelection(plan) {
  const section = $('selection'); section.replaceChildren(); section.hidden = false;
  section.append(element('h2', `已選方案：${plan.name}`), image(plan), element('p', price(plan), 'price'),
    element('p', plan.description), element('p', plan.participationRule, 'muted'),
    element('p', `包含：${plan.includedItems.join('、') || '依方案說明'}`, 'muted'),
    element('p', '此步僅選定方案。名額與庫存尚未確認，尚未建立預約。', 'muted'));
  if (plan.isDemo) section.append(element('p', '示範商品與測試價格，非正式販售承諾。', 'demo'));
  const ask = element('button', '請 AI 介紹這個方案', 'primary'); ask.dataset.action = 'ask';
  ask.addEventListener('click', () => run(async () => {
    await app.sendMessage({ role: 'user', content: [{ type: 'text', text: `我目前選擇 KINU TABI 方案「${plan.name}」（planId=${plan.id}），城市=${filters?.city}，成人總人數=${filters?.partySize}。請重新查詳情並說明方案人數規則與服務內容，尚未確認生成或建立預約。` }] });
    status('已請 AI 接續介紹。');
  }));
  section.append(ask);
  if (filters) {
    const start = element('button', '為每位旅客挑選和服', 'primary'); start.dataset.action = 'outfits';
    start.addEventListener('click', () => run(async () => {
      guests = Array.from({ length: filters.partySize }, () => ({ planId: plan.id, guestType: 'ADULT_FEMALE', kimonoId: null }));
      outfitSummary = null;
      await renderOutfits();
      await syncContext();
      status('請逐位選款；完成後檢查全員搭配。');
    }));
    section.append(start);
  }
}
async function loadGarments(planId) {
  const key = `${filters.city}:${planId}`;
  if (garments.has(key)) return garments.get(key);
  const values = [];
  let page = 0;
  do {
    const data = resultData(await app.callServerTool({ name: 'list_kimonos', arguments: { city: filters.city, planId, page } }));
    values.push(...data.kimonos); page = data.nextPage;
  } while (page !== null);
  garments.set(key, values);
  return values;
}
async function renderOutfits() {
  if (!selectedSlot) booking = null;
  if (!outfitSummary) { availability = null; availabilityFilters = null; selectedSlot = null; }
  const root = $('outfits'); root.hidden = false; root.replaceChildren(element('h2', '逐人挑選和服'));
  for (let i = 0; i < guests.length; i++) {
    const g = guests[i];
    const section = element('article'); section.append(element('h3', `旅客 ${i + 1}`));
    const planLabel = element('label', '方案'); const planSelect = element('select');
    for (const p of plans) { const option = element('option', p.name); option.value = p.id; planSelect.append(option); }
    planSelect.value = g.planId; planSelect.dataset.action = 'guest-plan';
    planSelect.addEventListener('change', () => run(async () => {
      g.planId = planSelect.value; g.kimonoId = null; outfitSummary = null;
      await renderOutfits(); await syncContext(); status('方案已變更，請重新選款並檢查搭配。');
    })); planLabel.append(planSelect); section.append(planLabel);
    const roleLabel = element('label', '和服類別'); const role = element('select'); role.dataset.action = 'role';
    for (const [value, label] of [['ADULT_FEMALE','女生'],['ADULT_MALE','男生']]) { const o = element('option', label); o.value = value; role.append(o); }
    role.value = g.guestType; role.addEventListener('change', () => run(async () => {
      g.guestType = role.value; g.kimonoId = null; outfitSummary = null;
      await renderOutfits(); await syncContext(); status('已變更類別，請重新選款。');
    })); roleLabel.append(role); section.append(roleLabel);
    const choices = element('div'); choices.style.cssText = 'display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px';
    const items = (await loadGarments(g.planId)).filter(k => `ADULT_${k.gender}` === g.guestType);
    if (!items.length) choices.append(element('p', '沒有符合此類別的款式，請更換方案或類別。'));
    for (const k of items) {
      const card = element('article'); card.append(image(k), element('h3', k.name), element('p', `${k.sku} · ${k.styleTags.join('、')}`, 'muted'));
      if (k.isDemo) card.append(element('p', '示範商品', 'demo'));
      const pick = element('button', g.kimonoId === k.id ? '已選擇 ✓' : '選擇此款', g.kimonoId === k.id ? 'primary' : ''); pick.dataset.action = 'garment';
      pick.addEventListener('click', () => run(async () => {
        g.kimonoId = k.id; outfitSummary = null;
        await renderOutfits(); await syncContext(); status(`已更新旅客 ${i + 1} 的款式，請重新檢查全員搭配。`);
      })); card.append(pick); choices.append(card);
    }
    section.append(choices); root.append(section);
  }
  root.append(element('h3', '全員搭配摘要'));
  for (let i = 0; i < guests.length; i++) {
    const g = guests[i]; const k = (await loadGarments(g.planId)).find(k => k.id === g.kimonoId);
    root.append(element('p', `旅客 ${i + 1}：${plans.find(p => p.id === g.planId)?.name || g.planId}／${k?.name || '尚未選款'}`));
    if (k) {
      const preview = element('button', `為旅客 ${i + 1} 開啟 AI 試穿`); preview.dataset.action = 'try-on';
      preview.addEventListener('click', () => run(async () => {
        await app.sendMessage({ role: 'user', content: [{ type: 'text', text: `請使用 kinutabi 的 show_try_on 為旅客 ${i + 1} 開啟試穿介面：planId=${g.planId}，kimonoId=${g.kimonoId}，conversationId=${tryOnConversationId}。目前只開啟人物來源選擇，尚未授權生成。` }] });
        status('已請 AI 開啟本人的試穿介面；需會員連線且每次生成另行確認。');
      })); root.append(preview);
    }
  }
  const check = element('button', '檢查全員搭配、估計金額與共同門市', 'primary'); check.dataset.action = 'summary';
  check.addEventListener('click', () => run(async () => {
    if (guests.some(g => !g.kimonoId)) throw new Error('請先為每位旅客選擇和服。');
    outfitSummary = null;
    await renderOutfits();
    const data = resultData(await app.callServerTool({ name: 'check_outfit_summary', arguments: { city: filters.city, guests } }));
    outfitSummary = data; await renderOutfits(); await syncContext(); status(data.notice);
  })); root.append(check);
  if (outfitSummary) {
    root.append(element('p', `全員估計金額：NT$${outfitSummary.estimatedTotal.toLocaleString('zh-TW')}`, 'price'));
    for (const line of outfitSummary.lineItems) root.append(element('p', `旅客 ${line.guestIndex + 1}：${line.label} NT$${line.total}`, 'muted'));
    root.append(element('h3', '共同適用門市'), element('p', outfitSummary.commonStores.map(s => s.name).join('、') || '沒有共同門市，請調整搭配。'), element('p', outfitSummary.notice, 'muted'));
    if (outfitSummary.isDemo) root.append(element('p', '示範商品／測試價格', 'demo'));
    if (outfitSummary.commonStores.length) renderAvailability(root);
  } else root.append(element('p', '目前搭配尚未完成檢查；金額與門市需重新確認。', 'muted'));
  controls();
}
function renderAvailability(root) {
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Tokyo', year:'numeric',month:'2-digit',day:'2-digit' }).format(new Date());
  const addDays = (day, count) => new Date(Date.parse(`${day}T00:00:00Z`) + count * 86400000).toISOString().slice(0, 10);
  availabilityFilters ||= { storeId: outfitSummary.commonStores[0].id, from: addDays(today, 1), to: addDays(today, 7) };
  root.append(element('h3', '全員可用日期與時段'), element('p', '日本時間（Asia/Tokyo）。可預約開始前至少 24 小時、未來 90 天內的時段；每次最多查 31 天。', 'muted'));
  const storeLabel = element('label', '共同門市'); const store = element('select'); store.dataset.action = 'availability-store';
  for (const item of outfitSummary.commonStores) { const option = element('option', item.name); option.value = item.id; store.append(option); }
  store.value = availabilityFilters.storeId; storeLabel.append(store); root.append(storeLabel);
  const changed = async () => { availability = null; selectedSlot = null; await renderOutfits(); await syncContext(); status('查詢條件已變更，請重新查詢全員可用時段。'); };
  store.addEventListener('change', () => run(async () => { availabilityFilters.storeId = store.value; await changed(); }));
  for (const [key, title] of [['from','開始日期'],['to','結束日期']]) {
    const label = element('label', title); const input = element('input'); input.type = 'date'; input.value = availabilityFilters[key];
    input.min = today; input.max = addDays(today, 90); input.dataset.action = `availability-${key}`;
    input.addEventListener('change', () => run(async () => { availabilityFilters[key] = input.value; await changed(); }));
    label.append(input); root.append(label);
  }
  const query = element('button', '查詢全員可用時段', 'primary'); query.dataset.action = 'availability-query';
  query.addEventListener('click', () => run(async () => {
    const {from,to} = availabilityFilters;
    const days = (Date.parse(`${to}T00:00:00Z`)-Date.parse(`${from}T00:00:00Z`))/86400000;
    availability = null; selectedSlot = null; await syncContext();
    if (!from || !to || !Number.isFinite(days) || days < 0 || days > 30) { await renderOutfits(); throw new Error('請選擇 1～31 天的有效日期區間。'); }
    await renderOutfits();
    availability = resultData(await app.callServerTool({ name:'check_party_availability', arguments:{city:filters.city,guests,...availabilityFilters} }));
    await renderOutfits(); await syncContext(); status(availability.notice);
  })); root.append(query);
  if (!availability) { root.append(element('p', '目前條件尚未查詢可用時間。', 'muted')); return; }
  const format = value => new Intl.DateTimeFormat('zh-TW', {timeZone:'Asia/Tokyo',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value));
  const reasons = {SLOT_CLOSED:'場次已關閉',OUTSIDE_BOOKING_WINDOW:'不在可預約範圍',SLOT_UNAVAILABLE:'場次已失效，請重查',SLOT_FULL:'全員接待名額不足',INVENTORY_UNAVAILABLE:'全員和服庫存不足（含整備時間）',RENTAL_AFTER_CLOSING:'歸還時間超過門市收件時間'};
  root.append(element('p', `查詢時間：${format(availability.serverTime)}（日本時間）`, 'muted'));
  if (availability.isDemo) root.append(element('p', '示範門市／商品／場次，非正式可售承諾。', 'demo'));
  if (!availability.slots.some(s => s.available)) root.append(element('p', '這段日期沒有全員可用時段。搭配已保留，可改查其他日期，或自行選擇另一共同門市。'));
  for (const slot of availability.slots) {
    const item = element('article'); item.append(element('p', `${format(slot.startsAt)} · ${slot.available ? '全員可用' : reasons[slot.reason] || '不可用'}`));
    if (slot.available) {
      item.append(element('p', `各旅客預計歸還：${slot.rentalEndsAt.map((end,i)=>`旅客 ${i+1} ${format(end)}`).join('；')}`, 'muted'));
      const choose = element('button', selectedSlot?.slotId === slot.slotId ? (booking?.view==='bookingHold'?'已暫留，待付款':'已選時段 ✓（未保留）') : '選擇此時段'); choose.dataset.action = 'availability-slot';
      choose.addEventListener('click', () => run(async () => { if(selectedSlot?.slotId!==slot.slotId)booking=null; selectedSlot = slot; await renderOutfits(); await syncContext(); status('已記錄時段偏好；尚未保留庫存或建立預約。'); })); item.append(choose);
    }
    root.append(item);
  }
  if (selectedSlot) renderBooking(root, format);
  root.append(element('p', availability.notice, 'muted'));
}
async function openPayment(url) {
  if (app.getHostCapabilities()?.openLinks) {
    try {
      await app.openLink({ url }, { timeout: 8000 });
      status('已請客戶端開啟官網。若未開啟，請使用卡片上的付款連結。');
      return;
    } catch { /* Keep the website link available on the card. */ }
  }
  status('請使用下方連結前往官網付款。');
}

function bookingLink(url, title) {
  const link = element('a', title);
  const parsed = new URL(url);
  if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password) throw new Error('官網連結格式無效。');
  link.href = parsed.href;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  return link;
}

function renderBooking(root, format) {
  const section = element('article');
  section.append(element('h3', '預約確認'));
  const prepare = async (replacement = {}) => {
    booking = resultData(await app.callServerTool({ name: 'prepare_booking',
      arguments: { storeId: availability.storeId, slotId: selectedSlot.slotId, guests, ...replacement } }));
    await renderOutfits();
    status(booking.notice || '已有不同內容的草稿，請選擇是否取代。');
  };
  if (booking?.view === 'bookingHold') {
    section.append(element('p', `暫留至 ${format(booking.expiresAt)}（日本時間）`),
      bookingLink(booking.paymentUrl, '開啟官網付款'), element('p', booking.paymentUrl, 'muted'));
    root.append(section);
    return;
  }
  if (booking?.view === 'bookingDraftConflict') {
    const replace = element('button', '確認取代未暫留草稿並報價');
    replace.dataset.action = 'booking-replace';
    replace.addEventListener('click', () => run(() => prepare({
      replaceDraftId: booking.draftId, replaceVersion: booking.version,
    })));
    section.append(element('p', '會員已有不同內容的草稿。取代後，原草稿的搭配和聯絡資料將換成這次選擇及會員資料。'),
      bookingLink(booking.websiteUrl, '到官網查看原草稿'), replace);
  } else if (booking?.view === 'bookingQuote') {
    section.append(element('p', `${booking.storeName} · ${format(booking.startsAt)}（日本時間）`));
    if (booking.isDemo) section.append(element('p', '示範資料 · Sandbox 付款', 'demo'));
    for (const item of booking.lineItems) section.append(element('p', `${item.name} · NT$${item.total.toLocaleString('zh-TW')}`));
    section.append(element('p', `總額 NT$${booking.total.toLocaleString('zh-TW')}`, 'price'), element('p', booking.notice, 'muted'));
    if (!booking.paymentAvailable) section.append(element('p', '官網 Sandbox 付款尚未啟用。'));
    const confirm = element('button', '確認並前往付款', 'primary');
    confirm.dataset.action = 'booking-confirm';
    confirm.dataset.unavailable = String(!booking.paymentAvailable);
    confirm.addEventListener('click', () => run(async () => {
      booking = resultData(await app.callServerTool({ name: 'confirm_booking_hold',
        arguments: { draftId: booking.draftId, quoteToken: booking.quoteToken, confirmed: true } }));
      await renderOutfits();
      await syncContext();
      await openPayment(booking.paymentUrl);
    }));
    section.append(confirm);
  }
  const quote = element('button', booking?.view === 'bookingQuote' ? '重新取得報價' : '使用會員資料並取得報價');
  quote.dataset.action = 'booking-quote';
  quote.addEventListener('click', () => run(() => prepare()));
  section.append(quote);
  root.append(section);
}

function render(data) {
  availability = null; availabilityFilters = null; selectedSlot = null; booking = null;
  $('notice').textContent = data.notice;
  if (data.view === 'plan') {
    selected = data.plan; guests = []; outfitSummary = null; $('outfits').hidden = true; $('outfits').replaceChildren();
    showSelection(selected); controls(); return;
  }
  filters = data.filters; nextPage = data.nextPage; selected = null; plans = data.plans;
  guests = []; outfitSummary = null; garments.clear(); $('outfits').hidden = true; $('outfits').replaceChildren();
  $('selection').hidden = true; $('selection').replaceChildren();
  $('city').value = filters.city; $('party-size').value = String(filters.partySize);
  $('keyword').value = filters.keyword; $('sort').value = filters.sort;
  $('page').textContent = `第 ${filters.page + 1} 頁 · 共 ${data.total} 個方案`;
  const container = $('plans'); container.replaceChildren();
  if (!data.plans.length) container.append(element('p', '沒有符合條件的方案，可更換城市或清除關鍵字。'));
  for (const plan of data.plans) {
    const card = element('article');
    card.append(image(plan), element('h3', plan.name), element('p', price(plan), 'price'), element('p', plan.summary),
      element('p', plan.participationRule, 'muted'), element('p', `適用門市：${plan.stores.map(s => s.name).join('、')}`, 'muted'));
    if (plan.isDemo) card.append(element('p', '示範商品／測試價格', 'demo'));
    const choose = element('button', '選擇並查看詳情'); choose.dataset.action = 'choose';
    choose.addEventListener('click', () => run(async () => {
      render(resultData(await app.callServerTool({ name: 'get_plan_details', arguments: { planId: plan.id } })));
      if (await syncContext()) status('已選定方案並同步摘要，可繼續向 AI 提問。');
    }));
    card.append(choose); container.append(card);
  }
  controls();
}
async function run(action) {
  if (busy) return;
  busy = true; controls(); status('處理中…');
  try { await action(); } catch (error) { status(error.message || '操作失敗，請重試。', true); }
  finally { busy = false; controls(); }
}
async function search(page) {
  await run(async () => {
    const input = { city: $('city').value, partySize: Number($('party-size').value), keyword: $('keyword').value.trim(), sort: $('sort').value, page, pageSize: filters?.pageSize || 6 };
    render(resultData(await app.callServerTool({ name: 'list_plans', arguments: input })));
    if (await syncContext()) status('方案已更新，可點選查看詳情。');
  });
}
$('filters').addEventListener('submit', event => { event.preventDefault(); void search(0); });
$('search').addEventListener('click', () => { void search(0); });
$('keyword').addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); void search(0); } });
$('previous').addEventListener('click', () => { void search(Math.max(0, filters.page - 1)); });
$('next').addEventListener('click', () => { if (nextPage !== null) void search(nextPage); });
app.ontoolresult = result => run(async () => {
  const data = resultData(result);
  if (data.view === 'partyAvailability') {
    filters = {city:data.city,partySize:data.guests.length,page:0,pageSize:6,keyword:'',sort:'recommended'};
    plans = await Promise.all([...new Set(data.guests.map(g=>g.planId))].map(async planId =>
      resultData(await app.callServerTool({name:'get_plan_details',arguments:{planId}})).plan));
    outfitSummary = resultData(await app.callServerTool({name:'check_outfit_summary',arguments:{city:data.city,guests:data.guests}}));
    guests = data.guests; availability = data; availabilityFilters = {storeId:data.storeId,from:data.from,to:data.to}; selectedSlot = null; selected = null; nextPage = null;
    $('selection').hidden = true; $('selection').replaceChildren(); $('plans').replaceChildren(); $('page').textContent = '';
    $('city').value = data.city; $('party-size').value = String(guests.length);
    $('keyword').value = ''; $('sort').value = 'recommended'; $('notice').textContent = data.notice;
    await renderOutfits(); await syncContext(); status(data.notice);
  } else { render(data); status('方案已載入，可點選查看詳情。'); }
});
if (window.parent === window) {
  status('請在支援 MCP Apps 的 AI 客戶端呼叫 show_plan_picker。直接開啟 HTML 不會連接 MCP。', true);
} else {
  app.connect().then(() => { connected = true; controls(); }).catch(() => {
    status('無法連接 MCP Apps 介面，請改以文字查詢或使用支援的客戶端。', true);
  });
}
