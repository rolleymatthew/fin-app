export class ApiError extends Error {
  constructor({ message, code, errorType, path, durationMs } = {}) {
    super(message || '请求失败');
    this.name = 'ApiError';
    this.code = code ?? -1;
    this.errorType = errorType ?? 'unknown';
    this.path = path ?? '';
    this.durationMs = durationMs ?? 0;
  }
}

async function _request(url, options) {
  const r = await fetch(url, options);
  const json = await r.json();
  if (!json || json.success !== true) {
    throw new ApiError({
      message: json?.message,
      code: json?.code,
      errorType: json?.errorType,
      path: json?.path,
      durationMs: json?.durationMs,
    });
  }
  return json.data;
}

export async function apiGet(url) {
  return _request(url);
}

export async function apiPost(url, body) {
  return _request(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
}