/**
 * /api/meetings/[id]/retry — proxies the retry POST to FastAPI.
 *
 * Session required. Upstream re-queues a failed meeting; 409 is returned if
 * the meeting is not in `failed` state.
 */
import { getServerSession } from 'next-auth/next';
import { NextResponse } from 'next/server';

import { authOptions } from '@/lib/auth';

const apiBaseUrl = (): string => process.env.API_BASE_URL ?? 'http://localhost:8000';

interface RouteContext {
  params: { id: string };
}

export async function POST(_req: Request, { params }: RouteContext): Promise<Response> {
  const session = await getServerSession(authOptions);
  if (!session?.user?.email) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }

  const upstream = await fetch(
    `${apiBaseUrl()}/meetings/${encodeURIComponent(params.id)}/retry`,
    { method: 'POST' },
  );
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { 'content-type': upstream.headers.get('content-type') ?? 'application/json' },
  });
}
