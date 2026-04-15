/**
 * @vitest-environment node
 *
 * /api/meetings/[id] — proxies GET (detail) and POST .../retry to FastAPI.
 * Unauthenticated callers never reach the upstream.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('next-auth/next', () => ({
  getServerSession: vi.fn(),
}));

vi.mock('@/lib/auth', () => ({
  authOptions: {},
}));

import { getServerSession } from 'next-auth/next';
import { GET } from '@/app/api/meetings/[id]/route';
import { POST as RETRY } from '@/app/api/meetings/[id]/retry/route';

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

describe('GET /api/meetings/[id]', () => {
  it('returns 401 when not signed in', async () => {
    vi.mocked(getServerSession).mockResolvedValue(null);

    const res = await GET(new Request('http://localhost/api/meetings/abc'), {
      params: { id: 'abc' },
    });

    expect(res.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('proxies to FastAPI by meeting id', async () => {
    signedInAs('alice@example.com');
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ id: 'm-1', status: 'complete' }), { status: 200 }),
    );

    const res = await GET(new Request('http://localhost/api/meetings/m-1'), {
      params: { id: 'm-1' },
    });

    expect(res.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('http://api.test/meetings/m-1');
    expect(init?.cache).toBe('no-store');
  });

  it('forwards upstream 404 through to the client', async () => {
    signedInAs('alice@example.com');
    fetchMock.mockResolvedValue(new Response('not found', { status: 404 }));

    const res = await GET(new Request('http://localhost/api/meetings/missing'), {
      params: { id: 'missing' },
    });

    expect(res.status).toBe(404);
  });
});

describe('POST /api/meetings/[id]/retry', () => {
  it('returns 401 when not signed in', async () => {
    vi.mocked(getServerSession).mockResolvedValue(null);

    const res = await RETRY(
      new Request('http://localhost/api/meetings/m-1/retry', { method: 'POST' }),
      { params: { id: 'm-1' } },
    );

    expect(res.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('forwards POST to the retry endpoint', async () => {
    signedInAs('alice@example.com');
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ id: 'm-1', status: 'queued' }), { status: 202 }),
    );

    const res = await RETRY(
      new Request('http://localhost/api/meetings/m-1/retry', { method: 'POST' }),
      { params: { id: 'm-1' } },
    );

    expect(res.status).toBe(202);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('http://api.test/meetings/m-1/retry');
    expect(init.method).toBe('POST');
  });
});
