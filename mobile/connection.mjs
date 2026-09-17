// Automatic refresh uses only an explicitly connected endpoint/token pair.
export function apiBase(value) {
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password)
    throw new Error('API 地址必须是 HTTP 或 HTTPS，且不能包含账号密码。');
  return url.origin;
}

export function initialConnection({origin, requested, fragment, savedBase, savedToken}) {
  let base;
  try { base = apiBase(requested || savedBase || origin); }
  catch { return {base: requested || '', token: '', automatic: false}; }
  const known = savedBase === base;
  return {base, token: fragment || (known ? savedToken : '') || '',
    automatic: (known && !fragment) || (base === origin && !!fragment)};
}

export function createConnection(fetcher, remember = () => {}) {
  let active = null, revision = 0, controller = null, busy = false;
  function disconnect() {
    revision++; active = null; busy = false;
    controller?.abort(); controller = null;
  }
  async function refresh() {
    if (!active || busy) return null;
    const current = active, epoch = revision;
    busy = true;
    const request = controller = new AbortController();
    const timeout = setTimeout(() => request.abort(), 15000);
    try {
      const response = await fetcher(new URL('/v1/jobs', current.base), {
        headers: {Authorization: 'Bearer ' + current.token}, signal: request.signal, redirect: 'error',
      });
      if (!response.ok) throw new Error(response.status === 401 ? '密钥不正确' : '连接失败（HTTP ' + response.status + '）');
      const items = await response.json();
      if (epoch !== revision) return null;
      if (!Array.isArray(items)) throw new Error('返回的任务列表格式不正确');
      remember(current.base, current.token);
      return items;
    } finally {
      clearTimeout(timeout);
      if (epoch === revision) { busy = false; controller = null; }
    }
  }
  return {
    disconnect, refresh,
    connect(base, token) {
      disconnect();
      if (!token.trim()) throw new Error('请填写访问密钥');
      active = {base: apiBase(base), token: token.trim()};
      return refresh();
    },
  };
}
