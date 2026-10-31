import test from 'node:test';
import assert from 'node:assert/strict';
import { transferPhoto } from '../ui/upload-diagnostics.mjs';

test('upload diagnostics distinguish CSP and timeout without exposing upload credentials', async () => {
  const upload = {photoId:'test-photo',grant:{url:'https://bucket.example/upload?secret=PRIVATE',fields:{policy:'PRIVATE'}}};
  for (const kind of ['csp','timeout','network','success']) {
    const events = new EventTarget();
    let removed = false;
    const remove = events.removeEventListener.bind(events);
    events.removeEventListener = (...args) => { removed=true;remove(...args); };
    const action = transferPhoto(upload, {}, {events,fetcher:async (url, options) => {
      assert.equal(options.mode,'no-cors');
      assert.equal(options.redirect,'follow');
      if (kind === 'success') return {};
      if (kind === 'csp') {
        const event = new Event('securitypolicyviolation');
        Object.assign(event,{blockedURI:url,effectiveDirective:'connect-src',disposition:'enforce'});
        setTimeout(() => events.dispatchEvent(event),0);
      }
      throw Object.assign(new Error('PRIVATE '+url),{name:kind === 'timeout' ? 'TimeoutError' : 'TypeError'});
    }});
    if (kind === 'success') await action;
    else await assert.rejects(action, error => {
      assert.ok(error.message.includes('test-photo'));
      assert.ok(error.message.includes('bucket.example'));
      assert.ok(!error.message.includes('PRIVATE'));
      assert.ok(!error.message.includes('?secret'));
      assert.ok(error.message.includes(kind === 'csp' ? 'CSP connect-src' : kind === 'timeout' ? '超過 60 秒' : '尚無證據'));
      return true;
    });
    assert.ok(removed);
  }
});

