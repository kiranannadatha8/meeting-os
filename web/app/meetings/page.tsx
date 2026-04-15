import { getServerSession } from 'next-auth/next';

import { authOptions } from '@/lib/auth';

export default async function MeetingsPage() {
  const session = await getServerSession(authOptions);

  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="text-2xl font-semibold">Meetings</h1>
      <p className="mt-2 text-sm text-slate-600">
        Signed in as {session?.user?.email ?? 'unknown'}
      </p>
      <p className="mt-6 text-slate-500">No meetings yet — upload one in T08.</p>
    </main>
  );
}
