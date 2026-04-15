/**
 * @vitest-environment node
 *
 * /api/meetings/[id]/dispatch/{linear,gmail} — proxies that inject the
 * signed-in user_id into the upstream POST body.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('next-auth/next', () => ({
  getServerSession: vi.fn(),
}));

vi.mock('@/lib/auth', () => ({
  authOptions: {},
}));

import { getServerSession } from 'next-auth/next';

import { POST as linearPost } from '@/app/api/meetings/[id]/dispatch/linear/route';
import { POST as gmailPost } from '@/app/api/meetings/[id]/dispatch/gmail/route';

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

describe('POST /api/meetings/[id]/dispatch/linear', () => {
  it('returns 401 when not signed in', async () => {
    vi.mocked(getServerSession).mockResolvedValue(null);
    const res = await linearPost(
      new Request('http://localhost/api/meetings/m-1/dispatch/linear', {
        method: 'POST',
        body: JSON.stringify({ team_id: 't', action_item_ids: ['a'] }),
      }),
      { params: { id: 'm-1' } },
    );
    expect(res.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('injects user_id into the forwarded body', async () => {
    signedInAs('kiran@example.com');
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ created: [], errors: [] }), { status: 200 }),
    );

    await linearPost(
      new Request('http://localhost/api/meetings/m-1/dispatch/linear', {
        method: 'POST',
        body: JSON.stringify({
          team_id: 't-uuid',
          action_item_ids: ['a-1'],
        }),
      }),
      { params: { id: 'm-1' } },
    );

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('http://api.test/meetings/m-1/dispatch/linear');
    expect(init.method).toBe('POST');
    expect(init.headers['content-type']).toBe('application/json');
    const body = JSON.parse(init.body);
    expect(body.user_id).toBe('kiran@example.com');
    expect(body.team_id).toBe('t-uuid');
    expect(body.action_item_ids).toEqual(['a-1']);
  });

  it('passes upstream status through', async () => {
    signedInAs('k@example.com');
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Linear not configured' }), { status: 409 }),
    );
    const res = await linearPost(
      new Request('http://localhost/api/meetings/m-1/dispatch/linear', {
        method: 'POST',
        body: JSON.stringify({ team_id: 't', action_item_ids: ['a'] }),
      }),
      { params: { id: 'm-1' } },
    );
    expect(res.status).toBe(409);
  });
});

describe('POST /api/meetings/[id]/dispatch/gmail', () => {
  it('returns 401 when not signed in', async () => {
    vi.mocked(getServerSession).mockResolvedValue(null);
    const res = await gmailPost(
      new Request('http://localhost/api/meetings/m-1/dispatch/gmail', {
        method: 'POST',
        body: JSON.stringify({ recipients: ['a@b.com'], action_item_ids: ['a'] }),
      }),
      { params: { id: 'm-1' } },
    );
    expect(res.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('injects user_id into the forwarded body', async () => {
    signedInAs('kiran@example.com');
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({ draft_id: 'd1', draft_url: 'https://mail.google.com/x' }),
        { status: 200 },
      ),
    );

    await gmailPost(
      new Request('http://localhost/api/meetings/m-1/dispatch/gmail', {
        method: 'POST',
        body: JSON.stringify({
          recipients: ['team@example.com'],
          action_item_ids: ['a-1'],
        }),
      }),
      { params: { id: 'm-1' } },
    );

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('http://api.test/meetings/m-1/dispatch/gmail');
    const body = JSON.parse(init.body);
    expect(body.user_id).toBe('kiran@example.com');
    expect(body.recipients).toEqual(['team@example.com']);
  });
});
