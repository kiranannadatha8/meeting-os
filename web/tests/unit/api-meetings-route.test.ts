/**
 * @vitest-environment node
 *
 * Route handlers proxy to FastAPI, attaching the session's user_id from
 * NextAuth. Unauthenticated callers get 401; the upstream is never hit.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('next-auth/next', () => ({
  getServerSession: vi.fn(),
}));

vi.mock('@/lib/auth', () => ({
  authOptions: {},
}));

import { getServerSession } from 'next-auth/next';
import { GET, POST } from '@/app/api/meetings/route';

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

describe('GET /api/meetings', () => {
  it('returns 401 when not signed in', async () => {
    vi.mocked(getServerSession).mockResolvedValue(null);

    const res = await GET(new Request('http://localhost/api/meetings'));

    expect(res.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('proxies to FastAPI with user_id from session', async () => {
    signedInAs('alice@example.com');
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify([{ id: 'm-1', title: 'x' }]), { status: 200 }),
    );

    const res = await GET(new Request('http://localhost/api/meetings'));

    expect(res.status).toBe(200);
    expect(await res.json()).toEqual([{ id: 'm-1', title: 'x' }]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url] = fetchMock.mock.calls[0];
    expect(url).toBe('http://api.test/meetings?user_id=alice%40example.com');
  });

  it('forwards upstream non-200 status', async () => {
    signedInAs('alice@example.com');
    fetchMock.mockResolvedValue(new Response('boom', { status: 502 }));

    const res = await GET(new Request('http://localhost/api/meetings'));

    expect(res.status).toBe(502);
  });
});

describe('POST /api/meetings', () => {
  it('returns 401 when not signed in', async () => {
    vi.mocked(getServerSession).mockResolvedValue(null);

    const form = new FormData();
    form.append('title', 't');
    form.append('file', new Blob(['x'], { type: 'text/plain' }), 'x.txt');

    const res = await POST(
      new Request('http://localhost/api/meetings', { method: 'POST', body: form }),
    );

    expect(res.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('forwards multipart body and injects user_id', async () => {
    signedInAs('bob@example.com');
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ id: 'm-9', status: 'queued' }), { status: 201 }),
    );

    const form = new FormData();
    form.append('title', 'Sync notes');
    form.append('file', new Blob(['hello'], { type: 'text/plain' }), 'notes.txt');

    const res = await POST(
      new Request('http://localhost/api/meetings', { method: 'POST', body: form }),
    );

    expect(res.status).toBe(201);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('http://api.test/meetings');
    expect(init.method).toBe('POST');
    const sentForm = init.body as FormData;
    expect(sentForm.get('user_id')).toBe('bob@example.com');
    expect(sentForm.get('title')).toBe('Sync notes');
    expect(sentForm.get('file')).toBeInstanceOf(File);
  });
});
