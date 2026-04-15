import { MeetingDetail } from '@/components/MeetingDetail';

interface PageProps {
  params: { id: string };
}

export default function MeetingDetailPage({ params }: PageProps): JSX.Element {
  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <MeetingDetail meetingId={params.id} />
    </main>
  );
}
