/**
 * /api/meetings — proxies to FastAPI, attaching the signed-in user_id from
 * the NextAuth session. Unauthenticated callers get 401; the upstream is
 * never reached.
 */
import { getServerSession } from 'next-auth/next';
import { NextResponse } from 'next/server';

import { authOptions } from '@/lib/auth';

const apiBaseUrl = (): string => process.env.API_BASE_URL ?? 'http://localhost:8000';

const userIdFromSession = async (): Promise<string | null> => {
  const session = await getServerSession(authOptions);
  const email = session?.user?.email;
  return email ?? null;
};

export async function GET(_req: Request): Promise<Response> {
  const userId = await userIdFromSession();
  if (!userId) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }

  const url = `${apiBaseUrl()}/meetings?user_id=${encodeURIComponent(userId)}`;
  const upstream = await fetch(url, { cache: 'no-store' });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { 'content-type': upstream.headers.get('content-type') ?? 'application/json' },
  });
}

export async function POST(req: Request): Promise<Response> {
  const userId = await userIdFromSession();
  if (!userId) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }

  const incoming = await req.formData();
  const outgoing = new FormData();
  for (const [key, value] of incoming.entries()) {
    outgoing.append(key, value);
  }
  outgoing.set('user_id', userId);

  const upstream = await fetch(`${apiBaseUrl()}/meetings`, {
    method: 'POST',
    body: outgoing,
  });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { 'content-type': upstream.headers.get('content-type') ?? 'application/json' },
  });
}
