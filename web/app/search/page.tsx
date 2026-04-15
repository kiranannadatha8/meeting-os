import { getServerSession } from 'next-auth/next';
import { redirect } from 'next/navigation';

import { SearchPanel } from '@/components/SearchPanel';
import { authOptions } from '@/lib/auth';

export default async function SearchPage() {
  const session = await getServerSession(authOptions);
  if (!session?.user?.email) {
    redirect('/signin');
  }

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold">Search</h1>
        <p className="mt-1 text-sm text-slate-600">
          Semantic search across your meeting transcripts.
        </p>
      </header>
      <SearchPanel />
    </main>
  );
}
