import { getServerSession } from 'next-auth/next';
import { redirect } from 'next/navigation';

import { MeetingsDashboard } from '@/components/MeetingsDashboard';
import { authOptions } from '@/lib/auth';

export default async function MeetingsPage() {
  const session = await getServerSession(authOptions);
  if (!session?.user?.email) {
    redirect('/signin');
  }

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold">Meetings</h1>
        <p className="mt-1 text-sm text-slate-600">Signed in as {session.user.email}</p>
      </header>
      <MeetingsDashboard />
    </main>
  );
}
