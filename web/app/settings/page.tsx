import { getServerSession } from 'next-auth/next';
import { redirect } from 'next/navigation';

import { SettingsPanel } from '@/components/SettingsPanel';
import { authOptions } from '@/lib/auth';

export default async function SettingsPage() {
  const session = await getServerSession(authOptions);
  if (!session?.user?.email) {
    redirect('/signin');
  }

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold">Integrations</h1>
        <p className="mt-1 text-sm text-slate-600">
          Connect Linear and Gmail so MeetingOS can create tickets and draft
          follow-ups. Keys are encrypted at rest.
        </p>
      </header>
      <SettingsPanel />
    </main>
  );
}
