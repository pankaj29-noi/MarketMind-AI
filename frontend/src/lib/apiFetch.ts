/**
 * Fetch helpers with cold-start awareness for Render free-tier wake-ups.
 *
 * A sleeping backend often returns 502/503/504 or a network failure on the first
 * request. Controlled retries with backoff recover without retry storms.
 */
import { API_BASE } from '@/lib/api';

const TRANSIENT = new Set([408, 425, 429, 502, 503, 504]);

export type ApiFetchOptions = RequestInit & {
  /** Total attempts including the first (default 3). */
  retries?: number;
  /** Base delay in ms before the first retry (default 1500). */
  retryDelayMs?: number;
  /** Called when a wake/retry is happening so the UI can show "waking backend…". */
  onRetry?: (attempt: number, reason: string) => void;
};

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function apiFetch(path: string, options: ApiFetchOptions = {}): Promise<Response> {
  const {
    retries = 3,
    retryDelayMs = 1500,
    onRetry,
    ...init
  } = options;

  const url = path.startsWith('http') ? path : `${API_BASE}${path.startsWith('/') ? '' : '/'}${path}`;
  let lastError: unknown;

  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      const res = await fetch(url, init);
      if (res.ok || !TRANSIENT.has(res.status) || attempt === retries) {
        return res;
      }
      onRetry?.(attempt, `HTTP ${res.status}`);
      await sleep(retryDelayMs * attempt);
    } catch (err) {
      lastError = err;
      if (attempt === retries) throw err;
      onRetry?.(attempt, err instanceof Error ? err.message : 'network error');
      await sleep(retryDelayMs * attempt);
    }
  }
  throw lastError instanceof Error ? lastError : new Error('Request failed after retries');
}

export async function checkApiHealth(timeoutMs = 8000): Promise<{
  ok: boolean;
  status: string;
  waking: boolean;
  body?: Record<string, unknown>;
}> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await apiFetch('/health', {
      method: 'GET',
      retries: 2,
      retryDelayMs: 2000,
      signal: controller.signal,
    });
    const body = await res.json().catch(() => ({}));
    const status = String((body as { status?: string }).status || (res.ok ? 'ok' : 'error'));
    return {
      ok: res.ok && status !== 'unavailable',
      status,
      waking: res.status === 503 || status === 'unavailable',
      body: body as Record<string, unknown>,
    };
  } catch {
    return { ok: false, status: 'unreachable', waking: true };
  } finally {
    clearTimeout(timer);
  }
}
