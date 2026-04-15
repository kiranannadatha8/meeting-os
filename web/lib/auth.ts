import type { NextAuthOptions } from 'next-auth';
import GoogleProvider from 'next-auth/providers/google';

const requireEnv = (key: string): string => {
  const value = process.env[key];
  if (!value) {
    throw new Error(`Missing required environment variable: ${key}`);
  }
  return value;
};

export const authOptions: NextAuthOptions = {
  providers: [
    GoogleProvider({
      clientId: requireEnv('GOOGLE_CLIENT_ID'),
      clientSecret: requireEnv('GOOGLE_CLIENT_SECRET'),
    }),
  ],
  session: { strategy: 'jwt' },
  pages: { signIn: '/signin' },
  callbacks: {
    async jwt({ token, account }) {
      if (account?.provider === 'google' && token.email) {
        token.userId = token.email;
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user && typeof token.userId === 'string') {
        (session.user as { id?: string }).id = token.userId;
      }
      return session;
    },
  },
};
