import type { MeetingSummary } from '@/lib/meeting-detail';

interface SummaryPanelProps {
  summary: MeetingSummary | null;
}

const MARKER_PATTERN = /\s*\[\[(?:decision|action):\d+\]\]/g;

const stripMarkers = (text: string): string => text.replace(MARKER_PATTERN, '').trim();

export function SummaryPanel({ summary }: SummaryPanelProps): JSX.Element {
  if (summary === null) {
    return <p className="text-sm text-slate-500">No summary yet.</p>;
  }
  return (
    <div className="rounded border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-sm text-slate-800">{stripMarkers(summary.tldr)}</p>
      <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-700">
        {summary.highlights.map((bullet, i) => (
          <li key={i}>{stripMarkers(bullet)}</li>
        ))}
      </ul>
    </div>
  );
}
