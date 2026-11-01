// 共享配置 / 响应解析（k6 场景通用，无副作用）
// 所有可调参数来自环境变量，配合 README 的“跑场景”一节。

export function cfg() {
  const raw = __ENV.PERF_BASE_URL || 'http://127.0.0.1:8000/api/v1';
  return {
    base: raw.replace(/\/+$/, ''),
    projectIds: (__ENV.PERF_PROJECT_ID || '')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean),
    toolId: __ENV.PERF_TOOL_ID || '',
    toolVersionId: __ENV.PERF_TOOL_VERSION_ID || '',
    pageSize: Number(__ENV.PERF_PAGE_SIZE || 50),
    deepPages: Number(__ENV.PERF_DEEP_PAGES || 0),
    think: Number(__ENV.PERF_THINK || 0.3),
  };
}

export function pick(list) {
  return list && list.length ? list[Math.floor(Math.random() * list.length)] : null;
}

// 兼容 {code,data:{items}} / {items} / data 直接是数组 三种信封
export function itemsOf(body) {
  if (!body || typeof body !== 'object') return [];
  const data = body.data && typeof body.data === 'object' ? body.data : body;
  if (Array.isArray(data.items)) return data.items;
  if (Array.isArray(body.items)) return body.items;
  if (Array.isArray(data)) return data;
  return [];
}

export function nextCursorOf(body) {
  if (!body || typeof body !== 'object') return '';
  const data = body.data && typeof body.data === 'object' ? body.data : body;
  return data.nextCursor || body.nextCursor || '';
}

export function idemKey() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
