/**
 * /api/search — proxies to FastAPI, attaching the signed-in user_id
 * as a query param. Unauthenticated callers get 401; callers without
 * a `q` parameter get 400 before the upstream is touched.
 */
import { getServerSession } from 'next-auth/next';
import { NextResponse } from 'next/server';

import { authOptions } from '@/lib/auth';

const apiBaseUrl = (): string => process.env.API_BASE_URL ?? 'http://localhost:8000';

export async function GET(req: Request): Promise<Response> {
  const session = await getServerSession(authOptions);
  const userId = session?.user?.email;
  if (!userId) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }

  const incoming = new URL(req.url);
  const q = incoming.searchParams.get('q');
  if (!q) {
    return NextResponse.json({ error: 'missing query' }, { status: 400 });
  }

  const params = new URLSearchParams({ q, user_id: userId });
  const limit = incoming.searchParams.get('limit');
  if (limit) params.set('limit', limit);

  const upstream = await fetch(`${apiBaseUrl()}/search?${params.toString()}`, {
    cache: 'no-store',
  });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { 'content-type': upstream.headers.get('content-type') ?? 'application/json' },
  });
}
