// read：读场景阶梯加压（默认 10 -> 50 -> 100 VU），覆盖结果/产物/任务列表（含深页）、任务详情
//   k6 run perf/k6/read.js
//   PERF_PROJECT_ID=<pid> PERF_DEEP_PAGES=40 k6 run perf/k6/read.js
import http from 'k6/http';
import { check, sleep } from 'k6';
import { login } from './lib/auth.js';
import { cfg, itemsOf, pick, nextCursorOf } from './lib/data.js';
import { READ_THRESHOLDS } from './lib/thresholds.js';

export const options = {
  scenarios: {
    read: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: __ENV.PERF_STAGE1 || '30s', target: Number(__ENV.PERF_VUS1 || 10) },
        { duration: __ENV.PERF_STAGE2 || '30s', target: Number(__ENV.PERF_VUS2 || 50) },
        { duration: __ENV.PERF_STAGE3 || '30s', target: Number(__ENV.PERF_VUS3 || 100) },
        { duration: __ENV.PERF_STAGE4 || '15s', target: 0 },
      ],
      gracefulStop: '15s',
    },
  },
  thresholds: READ_THRESHOLDS,
};

let c = null;
let authed = false;
let deepCursor = null;

function warmDeepCursor() {
  if (deepCursor !== null) return;
  const pid = c.projectIds[0];
  if (!c.deepPages) {
    deepCursor = '';
    return;
  }
  let cursor = '';
  for (let i = 0; i < c.deepPages; i++) {
    let url = `${c.base}/tasks?page_size=${c.pageSize}` + (pid ? `&project_id=${pid}` : '');
    if (cursor) url += `&cursor=${encodeURIComponent(cursor)}`;
    const r = http.get(url, { tags: { kind: 'list_deep_walk' } });
    if (r.status !== 200) break;
    cursor = nextCursorOf(r.json());
    if (!cursor) break;
  }
  deepCursor = cursor;
}

export default function () {
  if (!c) c = cfg();
  if (!authed) {
    login();
    authed = true;
    warmDeepCursor();
  }
  const pid = pick(c.projectIds);

  if (pid) {
    let r = http.get(`${c.base}/projects/${pid}/results?page_size=${c.pageSize}`, {
      tags: { kind: 'list_first_page' },
    });
    check(r, { '结果列表 200': (x) => x.status === 200 });

    r = http.get(`${c.base}/projects/${pid}/artifacts?page_size=${c.pageSize}`, {
      tags: { kind: 'list_first_page' },
    });
    check(r, { '产物列表 200': (x) => x.status === 200 });
  }

  let rt = http.get(
    `${c.base}/tasks?page_size=${c.pageSize}` + (pid ? `&project_id=${pid}` : ''),
    { tags: { kind: 'list_first_page' } }
  );
  check(rt, { '任务列表 200': (x) => x.status === 200 });

  const items = itemsOf(rt.json());
  if (items.length) {
    const tid = items[0].id;
    let rd = http.get(`${c.base}/tasks/${tid}`, { tags: { kind: 'detail' } });
    check(rd, { '任务详情 200': (x) => x.status === 200 });

    rd = http.get(`${c.base}/results/${tid}`, { tags: { kind: 'detail' } });
    check(rd, { '结果详情 200': (x) => x.status === 200 });
  }

  if (deepCursor) {
    const rDeep = http.get(
      `${c.base}/tasks?page_size=${c.pageSize}` +
        (pid ? `&project_id=${pid}` : '') +
        `&cursor=${encodeURIComponent(deepCursor)}`,
      { tags: { kind: 'list_deep' } }
    );
    check(rDeep, { '深页任务列表 200': (x) => x.status === 200 });
  }

  sleep(Math.random() * c.think);
}
