/**
 * @vitest-environment node
 *
 * `/api/meetings/[id]/events` proxies to FastAPI's SSE endpoint. It
 * forwards the upstream stream body (a `ReadableStream`) and preserves
 * the `text/event-stream` content-type so EventSource keeps the
 * connection open. Unauthenticated callers get 401 before any upstream
 * call.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('next-auth/next', () => ({
  getServerSession: vi.fn(),
}));

vi.mock('@/lib/auth', () => ({
  authOptions: {},
}));

import { getServerSession } from 'next-auth/next';

import { GET } from '@/app/api/meetings/[id]/events/route';

const fetchMock = vi.fn();
const originalFetch = global.fetch;

beforeEach(() => {
  process.env.API_BASE_URL = 'http://api.test';
  fetchMock.mockReset();
  global.fetch = fetchMock as unknown as typeof global.fetch;
  vi.mocked(getServerSession).mockReset();
});

afterEach(() => {
  global.fetch = originalFetch;
});

const signedInAs = (email: string) => {
  vi.mocked(getServerSession).mockResolvedValue({
    user: { email, id: email },
    expires: '2099-01-01',
  } as never);
};

describe('GET /api/meetings/[id]/events', () => {
  it('returns 401 when not signed in', async () => {
    vi.mocked(getServerSession).mockResolvedValue(null);

    const res = await GET(
      new Request('http://localhost/api/meetings/abc/events'),
      { params: { id: 'abc' } },
    );

    expect(res.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('proxies to FastAPI SSE endpoint and preserves event-stream content type', async () => {
    signedInAs('kiran@example.com');
    const body = 'event: status\ndata: {"status":"complete"}\n\n';
    fetchMock.mockResolvedValue(
      new Response(body, {
        status: 200,
        headers: { 'content-type': 'text/event-stream' },
      }),
    );

    const res = await GET(
      new Request('http://localhost/api/meetings/m-123/events'),
      { params: { id: 'm-123' } },
    );

    expect(res.status).toBe(200);
    expect(res.headers.get('content-type')).toBe('text/event-stream');
    expect(fetchMock).toHaveBeenCalledWith(
      'http://api.test/meetings/m-123/events',
      expect.objectContaining({ cache: 'no-store' }),
    );
    expect(await res.text()).toBe(body);
  });

  it('forwards upstream 404 when meeting is unknown', async () => {
    signedInAs('kiran@example.com');
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Meeting not found' }), {
        status: 404,
        headers: { 'content-type': 'application/json' },
      }),
    );

    const res = await GET(
      new Request('http://localhost/api/meetings/unknown/events'),
      { params: { id: 'unknown' } },
    );

    expect(res.status).toBe(404);
  });
});
