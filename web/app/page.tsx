import Link from 'next/link';

export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-4 p-8">
      <h1 className="text-3xl font-semibold">MeetingOS</h1>
      <p className="text-slate-600">Multi-agent meeting intelligence.</p>
      <Link
        href="/meetings"
        className="inline-flex w-fit items-center rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
      >
        Go to meetings
      </Link>
    </main>
  );
}
