/**
 * @vitest-environment node
 *
 * /api/integrations — proxies PUT (save), GET (status), DELETE to FastAPI,
 * attaching the signed-in user_id. Unauthenticated calls never reach upstream.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('next-auth/next', () => ({
  getServerSession: vi.fn(),
}));

vi.mock('@/lib/auth', () => ({
  authOptions: {},
}));

import { getServerSession } from 'next-auth/next';

import { DELETE, GET, PUT } from '@/app/api/integrations/route';

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

describe('GET /api/integrations', () => {
  it('returns 401 when not signed in', async () => {
    vi.mocked(getServerSession).mockResolvedValue(null);

    const res = await GET(new Request('http://localhost/api/integrations'));

    expect(res.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('proxies status with user_id injected from session', async () => {
    signedInAs('kiran@example.com');
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ linear: true, gmail: false }), { status: 200 }),
    );

    const res = await GET(new Request('http://localhost/api/integrations'));

    expect(res.status).toBe(200);
    const [url] = fetchMock.mock.calls[0];
    expect(url).toBe('http://api.test/integrations/status?user_id=kiran%40example.com');
  });
});

describe('PUT /api/integrations', () => {
  it('returns 401 when not signed in', async () => {
    vi.mocked(getServerSession).mockResolvedValue(null);

    const res = await PUT(
      new Request('http://localhost/api/integrations', {
        method: 'PUT',
        body: JSON.stringify({ provider: 'linear', api_key: 'k' }),
      }),
    );

    expect(res.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('injects session user_id into the forwarded body', async () => {
    signedInAs('kiran@example.com');
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ status: 'ok' }), { status: 200 }),
    );

    const res = await PUT(
      new Request('http://localhost/api/integrations', {
        method: 'PUT',
        body: JSON.stringify({ provider: 'linear', api_key: 'plaintext' }),
      }),
    );

    expect(res.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('http://api.test/integrations');
    expect(init.method).toBe('PUT');
    expect(init.headers['content-type']).toBe('application/json');
    expect(JSON.parse(init.body as string)).toEqual({
      provider: 'linear',
      api_key: 'plaintext',
      user_id: 'kiran@example.com',
    });
  });
});

describe('DELETE /api/integrations', () => {
  it('returns 401 when not signed in', async () => {
    vi.mocked(getServerSession).mockResolvedValue(null);

    const res = await DELETE(
      new Request('http://localhost/api/integrations?provider=linear', { method: 'DELETE' }),
    );

    expect(res.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('forwards provider + user_id to FastAPI', async () => {
    signedInAs('kiran@example.com');
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));

    const res = await DELETE(
      new Request('http://localhost/api/integrations?provider=linear', { method: 'DELETE' }),
    );

    expect(res.status).toBe(204);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      'http://api.test/integrations?user_id=kiran%40example.com&provider=linear',
    );
    expect(init.method).toBe('DELETE');
  });
});
