// 登录 / Cookie / CSRF 辅助（与后端 auth/dependencies.py 约定一致）
//   登录：POST /auth/login -> 服务端 Set-Cookie: cpumodel_access / cpumodel_csrf
//   写请求：header X-CSRF-Token = cpumodel_csrf cookie（否则 403 "CSRF 校验失败"）
import http from 'k6/http';
import { check } from 'k6';
import { cfg } from './data.js';

export function login() {
  const c = cfg();
  const res = http.post(
    `${c.base}/auth/login`,
    JSON.stringify({
      username: __ENV.PERF_USERNAME || 'perf_user',
      password: __ENV.PERF_PASSWORD || '',
    }),
    { headers: { 'Content-Type': 'application/json' }, tags: { kind: 'login' } }
  );
  check(res, { '登录成功 (200)': (r) => r.status === 200 });
  return { csrf: getCsrf(c.base) };
}

// 从 k6 的 VU cookie jar 读取 cpumodel_csrf
export function getCsrf(base) {
  try {
    const jar = http.cookieJar();
    const cookies = jar.cookiesForURL(base);
    const v = cookies['cpumodel_csrf'];
    if (Array.isArray(v)) return v[0] || '';
    return v || '';
  } catch (e) {
    return '';
  }
}

export function jsonHeaders(csrf) {
  const h = { 'Content-Type': 'application/json' };
  if (csrf) h['X-CSRF-Token'] = csrf;
  return h;
}

export function plainHeaders(csrf) {
  const h = {};
  if (csrf) h['X-CSRF-Token'] = csrf;
  return h;
}
