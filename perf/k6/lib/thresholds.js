// SLO 阈值（对应阶段 4.1；tag 名与各场景里 http.*(tags.kind) 对齐）
//   kind=list_first_page  -> 列表首屏 P95 <= 300ms
//   kind=detail           -> 详情 P95 <= 150ms
//   kind=task_submit      -> 提交任务 P95 <= 800ms
//   kind=upload_meta      -> 上传（元数据）P95 <= 1000ms
//   错误率 < 0.5%（不含 4xx 业务拒绝；http_req_failed 只统计网络/5xx 级失败）

export const SMOKE_THRESHOLDS = {
  http_req_failed: ['rate<0.01'],
  checks: ['rate>0.99'],
};

export const READ_THRESHOLDS = {
  http_req_failed: ['rate<0.005'],
  'http_req_duration{kind:list_first_page}': ['p(95)<300'],
  'http_req_duration{kind:detail}': ['p(95)<150'],
  'http_req_duration{kind:list_deep}': ['p(95)<600'],
  checks: ['rate>0.99'],
};

export const WRITE_THRESHOLDS = {
  http_req_failed: ['rate<0.005'],
  'http_req_duration{kind:task_submit}': ['p(95)<800'],
  'http_req_duration{kind:upload_meta}': ['p(95)<1000'],
  'http_req_duration{kind:create_project}': ['p(95)<800'],
  checks: ['rate>0.99'],
};

export const MIXED_THRESHOLDS = {
  http_req_failed: ['rate<0.005'],
  'http_req_duration{kind:list_first_page}': ['p(95)<300'],
  'http_req_duration{kind:detail}': ['p(95)<150'],
  'http_req_duration{kind:task_submit}': ['p(95)<800'],
  'http_req_duration{kind:upload_meta}': ['p(95)<1000'],
  checks: ['rate>0.99'],
};
