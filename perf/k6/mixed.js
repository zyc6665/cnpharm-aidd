// mixed：70% 读 / 30% 写 的 soak（默认 30min，可用 PERF_HOLD 覆盖）
//   PERF_PROJECT_ID=<pid> PERF_TOOL_ID=<tid> PERF_HOLD=30m k6 run perf/k6/mixed.js
import http from 'k6/http';
import { check, sleep } from 'k6';
import { login, jsonHeaders, plainHeaders } from './lib/auth.js';
import { cfg, itemsOf, pick, idemKey } from './lib/data.js';
import { MIXED_THRESHOLDS } from './lib/thresholds.js';

export const options = {
  scenarios: {
    mixed: {
      executor: 'constant-vus',
      vus: Number(__ENV.PERF_VUS || 50),
      duration: __ENV.PERF_HOLD || '30m',
      gracefulStop: '30s',
    },
  },
  thresholds: MIXED_THRESHOLDS,
};

let c = null;
let authed = false;
let csrf = '';

function doRead() {
  const pid = pick(c.projectIds);
  let r;
  if (pid) {
    r = http.get(`${c.base}/projects/${pid}/results?page_size=${c.pageSize}`, {
      tags: { kind: 'list_first_page' },
    });
    check(r, { '结果列表 200': (x) => x.status === 200 });
    r = http.get(`${c.base}/projects/${pid}/artifacts?page_size=${c.pageSize}`, {
      tags: { kind: 'list_first_page' },
    });
    check(r, { '产物列表 200': (x) => x.status === 200 });
  }
  r = http.get(
    `${c.base}/tasks?page_size=${c.pageSize}` + (pid ? `&project_id=${pid}` : ''),
    { tags: { kind: 'list_first_page' } }
  );
  check(r, { '任务列表 200': (x) => x.status === 200 });
  const items = itemsOf(r.json());
  if (items.length) {
    const tid = items[0].id;
    const rd = http.get(`${c.base}/tasks/${tid}`, { tags: { kind: 'detail' } });
    check(rd, { '任务详情 200': (x) => x.status === 200 });
  }
}

function doWrite() {
  const pid = pick(c.projectIds);
  const name = `perf_k6_mixed_${Date.now()}_${Math.floor(Math.random() * 1e6)}`;
  let r = http.post(`${c.base}/projects`, JSON.stringify({ name, goal: 'k6 mixed' }), {
    headers: jsonHeaders(csrf),
    tags: { kind: 'create_project' },
  });
  check(r, { '创建项目 2xx': (x) => x.status >= 200 && x.status < 300 });

  if (c.toolId) {
    const payload = { name: `perf_k6_mixed_task_${Date.now()}`, tool_id: c.toolId, params: {} };
    if (pid) payload.project_id = pid;
    if (c.toolVersionId) payload.tool_version_id = c.toolVersionId;
    r = http.post(`${c.base}/tasks`, JSON.stringify(payload), {
      headers: Object.assign(jsonHeaders(csrf), { 'X-Idempotency-Key': idemKey() }),
      tags: { kind: 'task_submit' },
    });
    check(r, { '提交任务 2xx': (x) => x.status >= 200 && x.status < 300 });
  }

  const fileBody = 'perf load small file\n'.repeat(8);
  r = http.post(
    `${c.base}/files/upload`,
    { file: http.file(fileBody, 'perf_small.txt', 'text/plain') },
    { headers: plainHeaders(csrf), tags: { kind: 'upload_meta' } }
  );
  check(r, { '上传小文件 2xx': (x) => x.status >= 200 && x.status < 300 });
}

export default function () {
  if (!c) c = cfg();
  if (!authed) {
    csrf = login().csrf;
    authed = true;
  }
  const writeRatio = Number(__ENV.PERF_WRITE_RATIO || 0.3);
  if (Math.random() < writeRatio) {
    doWrite();
  } else {
    doRead();
  }
  sleep(Math.random() * c.think);
}
