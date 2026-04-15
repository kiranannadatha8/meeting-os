import { describe, expect, it } from 'vitest';

describe('middleware matcher', () => {
  it('guards /meetings and any nested path', async () => {
    const mod = await import('@/middleware');
    const { config } = mod;
    expect(config.matcher).toEqual(
      expect.arrayContaining(['/meetings/:path*']),
    );
  });
});
