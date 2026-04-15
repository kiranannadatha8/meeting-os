/**
 * /api/meetings/[id]/events — SSE proxy to FastAPI.
 *
 * Passes the upstream ReadableStream through unchanged so EventSource
 * clients see a continuous text/event-stream. Auth is enforced up
 * front; unsigned-in callers never hit the upstream.
 */
import { getServerSession } from 'next-auth/next';
import { NextResponse } from 'next/server';

import { authOptions } from '@/lib/auth';

export const dynamic = 'force-dynamic';

const apiBaseUrl = (): string => process.env.API_BASE_URL ?? 'http://localhost:8000';

interface RouteContext {
  params: { id: string };
}

export async function GET(_req: Request, { params }: RouteContext): Promise<Response> {
  const session = await getServerSession(authOptions);
  if (!session?.user?.email) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }

  const upstream = await fetch(`${apiBaseUrl()}/meetings/${params.id}/events`, {
    cache: 'no-store',
  });

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      'content-type':
        upstream.headers.get('content-type') ?? 'text/event-stream',
      'cache-control': 'no-cache',
      connection: 'keep-alive',
    },
  });
}
