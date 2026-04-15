/**
 * @vitest-environment node
 *
 * `/api/search` proxies to FastAPI with the signed-in user_id appended
 * as a query param. Unauthenticated callers get 401 and never reach
 * the upstream.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('next-auth/next', () => ({
  getServerSession: vi.fn(),
}));

vi.mock('@/lib/auth', () => ({
  authOptions: {},
}));

import { getServerSession } from 'next-auth/next';

import { GET } from '@/app/api/search/route';

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

describe('GET /api/search', () => {
  it('returns 401 when not signed in', async () => {
    vi.mocked(getServerSession).mockResolvedValue(null);

    const res = await GET(new Request('http://localhost/api/search?q=pricing'));

    expect(res.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('proxies query + user_id to FastAPI', async () => {
    signedInAs('kiran@example.com');
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ results: [] }), { status: 200 }),
    );

    const res = await GET(
      new Request('http://localhost/api/search?q=pricing%20model'),
    );

    expect(res.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url] = fetchMock.mock.calls[0];
    expect(url).toBe(
      'http://api.test/search?q=pricing+model&user_id=kiran%40example.com',
    );
  });

  it('returns 400 when q is missing', async () => {
    signedInAs('kiran@example.com');

    const res = await GET(new Request('http://localhost/api/search'));

    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('forwards upstream non-200 status', async () => {
    signedInAs('kiran@example.com');
    fetchMock.mockResolvedValue(new Response('boom', { status: 500 }));

    const res = await GET(new Request('http://localhost/api/search?q=x'));

    expect(res.status).toBe(500);
  });
});
