/**
 * /api/integrations — proxies the FastAPI integration endpoints.
 *
 * The signed-in user_id is injected on every request so the browser never
 * gets to pick whose keys it manages. Unauthenticated calls short-circuit
 * with 401; the upstream is never reached.
 */
import { getServerSession } from 'next-auth/next';
import { NextResponse } from 'next/server';

import { authOptions } from '@/lib/auth';

const apiBaseUrl = (): string => process.env.API_BASE_URL ?? 'http://localhost:8000';

const userIdFromSession = async (): Promise<string | null> => {
  const session = await getServerSession(authOptions);
  return session?.user?.email ?? null;
};

const unauthorized = (): Response =>
  NextResponse.json({ error: 'unauthorized' }, { status: 401 });

const forwardBody = (upstream: Response): Response =>
  new Response(upstream.body, {
    status: upstream.status,
    headers: {
      'content-type': upstream.headers.get('content-type') ?? 'application/json',
    },
  });

export async function GET(_req: Request): Promise<Response> {
  const userId = await userIdFromSession();
  if (!userId) return unauthorized();

  const url = `${apiBaseUrl()}/integrations/status?user_id=${encodeURIComponent(userId)}`;
  const upstream = await fetch(url, { cache: 'no-store' });
  return forwardBody(upstream);
}

export async function PUT(req: Request): Promise<Response> {
  const userId = await userIdFromSession();
  if (!userId) return unauthorized();

  const body = (await req.json()) as Record<string, unknown>;
  const upstream = await fetch(`${apiBaseUrl()}/integrations`, {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ ...body, user_id: userId }),
  });
  return forwardBody(upstream);
}

export async function DELETE(req: Request): Promise<Response> {
  const userId = await userIdFromSession();
  if (!userId) return unauthorized();

  const provider = new URL(req.url).searchParams.get('provider');
  if (!provider) {
    return NextResponse.json({ error: 'provider is required' }, { status: 400 });
  }

  const url =
    `${apiBaseUrl()}/integrations?user_id=${encodeURIComponent(userId)}` +
    `&provider=${encodeURIComponent(provider)}`;
  const upstream = await fetch(url, { method: 'DELETE' });
  return forwardBody(upstream);
}
