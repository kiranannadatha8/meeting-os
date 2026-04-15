import { describe, expect, it, beforeEach } from 'vitest';

describe('authOptions', () => {
  beforeEach(() => {
    process.env.GOOGLE_CLIENT_ID = 'test-client-id';
    process.env.GOOGLE_CLIENT_SECRET = 'test-client-secret';
    process.env.NEXTAUTH_SECRET = 'test-secret';
  });

  it('configures a Google provider with env-bound credentials', async () => {
    const { authOptions } = await import('@/lib/auth');

    expect(authOptions.providers).toHaveLength(1);
    const google = authOptions.providers[0] as { id: string; options?: { clientId?: string } };
    expect(google.id).toBe('google');
    expect(google.options?.clientId).toBe('test-client-id');
  });

  it('uses JWT session strategy (no DB-backed sessions)', async () => {
    const { authOptions } = await import('@/lib/auth');
    expect(authOptions.session?.strategy).toBe('jwt');
  });

  it('routes sign-in to the custom /signin page', async () => {
    const { authOptions } = await import('@/lib/auth');
    expect(authOptions.pages?.signIn).toBe('/signin');
  });
});
