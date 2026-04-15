/**
 * /api/meetings/[id]/dispatch/gmail — proxy that injects the signed-in
 * user_id into the upstream body. The FastAPI handler trusts the proxy.
 */
import { getServerSession } from 'next-auth/next';
import { NextResponse } from 'next/server';

import { authOptions } from '@/lib/auth';

const apiBaseUrl = (): string => process.env.API_BASE_URL ?? 'http://localhost:8000';

interface RouteContext {
  params: { id: string };
}

export async function POST(req: Request, { params }: RouteContext): Promise<Response> {
  const session = await getServerSession(authOptions);
  const userId = session?.user?.email;
  if (!userId) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }

  const body = (await req.json()) as Record<string, unknown>;
  const upstream = await fetch(
    `${apiBaseUrl()}/meetings/${encodeURIComponent(params.id)}/dispatch/gmail`,
    {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ ...body, user_id: userId }),
    },
  );
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { 'content-type': upstream.headers.get('content-type') ?? 'application/json' },
  });
}
