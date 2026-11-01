// smoke：1 VU 单轮自检，验证登录(Cookie+CSRF)与核心读路径连通
//   k6 run perf/k6/smoke.js
import http from 'k6/http';
import { check } from 'k6';
import { login } from './lib/auth.js';
import { cfg, itemsOf } from './lib/data.js';
import { SMOKE_THRESHOLDS } from './lib/thresholds.js';

export const options = {
  vus: 1,
  iterations: 1,
  thresholds: SMOKE_THRESHOLDS,
};

let authed = false;

export default function () {
  const c = cfg();
  if (!authed) {
    login();
    authed = true;
  }
  const pid = c.projectIds[0] || null;

  const proj = http.get(`${c.base}/projects`, { tags: { kind: 'list_first_page' } });
  check(proj, { '项目列表 200': (r) => r.status === 200 });

  if (pid) {
    const rr = http.get(`${c.base}/projects/${pid}/results?page_size=10`, {
      tags: { kind: 'list_first_page' },
    });
    check(rr, { '结果列表 200': (r) => r.status === 200 });

    const ra = http.get(`${c.base}/projects/${pid}/artifacts?page_size=10`, {
      tags: { kind: 'list_first_page' },
    });
    check(ra, { '产物列表 200': (r) => r.status === 200 });
  }

  const rt = http.get(
    `${c.base}/tasks?page_size=10` + (pid ? `&project_id=${pid}` : ''),
    { tags: { kind: 'list_first_page' } }
  );
  check(rt, { '任务列表 200': (r) => r.status === 200 });

  const items = itemsOf(rt.json());
  if (items.length) {
    const tid = items[0].id;
    const rd = http.get(`${c.base}/tasks/${tid}`, { tags: { kind: 'detail' } });
    check(rd, { '任务详情 200': (r) => r.status === 200 });
  }
}
