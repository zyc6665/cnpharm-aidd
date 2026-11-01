// write：写场景——创建项目、提交任务（X-Idempotency-Key）、小文件上传
// 注意：提交任务会在后端真实建任务并（尝试）调度；建议配合专用的 no-op 工具（perf_seed 已建）。
//   PERF_PROJECT_ID=<pid> PERF_TOOL_ID=<tid> k6 run perf/k6/write.js
import http from 'k6/http';
import { check, sleep } from 'k6';
import { login, jsonHeaders, plainHeaders } from './lib/auth.js';
import { cfg, pick, idemKey } from './lib/data.js';
import { WRITE_THRESHOLDS } from './lib/thresholds.js';

export const options = {
  scenarios: {
    write: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: __ENV.PERF_STAGE1 || '30s', target: Number(__ENV.PERF_VUS1 || 5) },
        { duration: __ENV.PERF_STAGE2 || '30s', target: Number(__ENV.PERF_VUS2 || 20) },
        { duration: __ENV.PERF_STAGE3 || '15s', target: 0 },
      ],
      gracefulStop: '15s',
    },
  },
  thresholds: WRITE_THRESHOLDS,
};

let c = null;
let authed = false;
let csrf = '';

export default function () {
  if (!c) c = cfg();
  if (!authed) {
    csrf = login().csrf;
    authed = true;
  }
  const pid = pick(c.projectIds);

  // 1) 创建项目
  const name = `perf_k6_proj_${Date.now()}_${Math.floor(Math.random() * 1e6)}`;
  let r = http.post(`${c.base}/projects`, JSON.stringify({ name, goal: 'k6 write load' }), {
    headers: jsonHeaders(csrf),
    tags: { kind: 'create_project' },
  });
  check(r, { '创建项目 200/201': (x) => x.status === 200 || x.status === 201 });

  // 2) 提交任务
  if (c.toolId) {
    const payload = { name: `perf_k6_task_${Date.now()}`, tool_id: c.toolId, params: {} };
    if (pid) payload.project_id = pid;
    if (c.toolVersionId) payload.tool_version_id = c.toolVersionId;
    r = http.post(`${c.base}/tasks`, JSON.stringify(payload), {
      headers: Object.assign(jsonHeaders(csrf), { 'X-Idempotency-Key': idemKey() }),
      tags: { kind: 'task_submit' },
    });
    check(r, { '提交任务 2xx': (x) => x.status >= 200 && x.status < 300 });
  }

  // 3) 小文件上传（multipart，字段名 file）
  const fileBody = 'perf load small file\n'.repeat(8);
  r = http.post(
    `${c.base}/files/upload`,
    { file: http.file(fileBody, 'perf_small.txt', 'text/plain') },
    { headers: plainHeaders(csrf), tags: { kind: 'upload_meta' } }
  );
  check(r, { '上传小文件 2xx': (x) => x.status >= 200 && x.status < 300 });

  sleep(Math.random() * c.think);
}
