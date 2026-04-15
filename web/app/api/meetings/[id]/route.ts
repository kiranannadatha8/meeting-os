/**
 * /api/meetings/[id] — proxies the detail GET to FastAPI.
 *
 * Authorization is session-only: if you're signed in, you can read your own
 * meetings. Backend-level ACLs (filter by user_id on retrieve) will move in
 * here in a later phase; for now the upstream trusts the proxy.
 */
import { getServerSession } from 'next-auth/next';
import { NextResponse } from 'next/server';

import { authOptions } from '@/lib/auth';

const apiBaseUrl = (): string => process.env.API_BASE_URL ?? 'http://localhost:8000';

interface RouteContext {
  params: { id: string };
}

export async function GET(_req: Request, { params }: RouteContext): Promise<Response> {
  const session = await getServerSession(authOptions);
  if (!session?.user?.email) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }

  const upstream = await fetch(`${apiBaseUrl()}/meetings/${encodeURIComponent(params.id)}`, {
    cache: 'no-store',
  });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { 'content-type': upstream.headers.get('content-type') ?? 'application/json' },
  });
}
