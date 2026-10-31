// Never include signed URLs, form fields or photo contents in diagnostics.
export async function transferPhoto(upload, form, {events=globalThis.document, fetcher=globalThis.fetch}={}) {
  const host = new URL(upload.grant.url).host;
  const started = performance.now();
  let blocked = '';
  const onViolation = event => {
    let blockedHost;
    try { blockedHost = new URL(event.blockedURI).host; } catch { return; }
    if (blockedHost === host && event.disposition === 'enforce' && event.effectiveDirective === 'connect-src') blocked = 'connect-src';
  };
  events.addEventListener('securitypolicyviolation', onViolation);
  try {
    await fetcher(upload.grant.url, {method:'POST',body:form,mode:'no-cors',credentials:'omit',redirect:'follow',referrerPolicy:'no-referrer',signal:AbortSignal.timeout(60000)});
  } catch (error) {
    // CSP events can be dispatched just after fetch rejects.
    await new Promise(resolve => setTimeout(resolve, 100));
    const name = ['TimeoutError','AbortError','TypeError','SecurityError'].includes(error?.name) ? error.name : 'UnknownError';
    const reason = blocked ? '客戶端 CSP connect-src 已阻擋上傳連線。' : name === 'TimeoutError' ? '上傳超過 60 秒。' : '連線失敗；尚無證據區分網路、重新導向或客戶端限制，也不能判定為 CORS。';
    throw new Error(`照片傳輸未完成，可重試本次上傳，或改用官網備援。\n上傳診斷：${reason}\n錯誤：${name}；耗時：${((performance.now()-started)/1000).toFixed(1)} 秒；主機：${host}；photoId：${upload.photoId}`);
  } finally {
    events.removeEventListener('securitypolicyviolation', onViolation);
  }
}
