// Connects the UI to the PinguinoSuite core in all three hosts: Tauri shell, core-served page, or plain browser.
// Relative fetch('/api/..') calls are rewritten to the core base URL with the per-launch token attached.
(() => {
  const nativeFetch = window.fetch.bind(window);
  let cfg = null;
  const ready = (async () => {
    const T = window.__TAURI__;
    if (T && T.core) {
      cfg = await T.core.invoke('core_config');           // {base, token}
    } else {
      const m = document.querySelector('meta[name="pinguino-token"]');
      cfg = { base: location.origin, token: m ? m.content : '' };
    }
  })();
  window.fetch = async (url, opts = {}) => {
    if (typeof url === 'string' && url.startsWith('/')) {
      await ready;
      opts = { ...opts, headers: { ...(opts.headers || {}), Authorization: 'Bearer ' + cfg.token } };
      url = cfg.base + url;
    }
    return nativeFetch(url, opts);
  };
  window.PG = { ready, ws: () => open() };
  function open() {
    const proxy = { onmessage: null, onclose: null };
    ready.then(() => {
      const u = new URL(cfg.base); 
      const w = new WebSocket(`ws://${u.host}/ws?token=${encodeURIComponent(cfg.token)}`);
      w.onmessage = e => proxy.onmessage && proxy.onmessage(e);
      w.onclose = e => proxy.onclose && proxy.onclose(e);
    });
    return proxy;
  }
})();
