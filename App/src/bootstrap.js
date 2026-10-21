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
  // Pop-out windows (Tauri shell only; see src-tauri/src/windows.rs). Each call rejects with "not in the app" in a plain browser.
  const inv = (cmd, args) => (window.__TAURI__ && window.__TAURI__.core) ? window.__TAURI__.core.invoke(cmd, args) : Promise.reject(new Error('Pop-out windows need the PinguinoSuite app'));
  window.PGWin = {
    monitors: () => inv('list_monitors'),
    list: () => inv('list_windows'),
    open: req => inv('open_window', { req }),                 // {label, url, title?, width?, height?, monitor?, place?: full|top|bottom|left|right, always_on_top?, decorations?, reset?}
    close: (label, forget) => inv('close_window', { label, forget: !!forget }),
    onTop: (label, on) => inv('set_window_on_top', { label, on }),
    openSite: path => inv('open_site_window', { path: path || null }),   // the website in its own window (own icon, taskbar entry and login profile); optional path like '/customs'
    clearSiteData: () => inv('clear_site_data'),                          // forget the site login (close the site window first)
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
