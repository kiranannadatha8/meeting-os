import type { Decision } from '@/lib/meeting-detail';

interface DecisionCardProps {
  decision: Decision;
}

export function DecisionCard({ decision }: DecisionCardProps): JSX.Element {
  return (
    <article className="rounded border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-slate-900">{decision.title}</h3>
      <p className="mt-2 text-sm text-slate-700">{decision.rationale}</p>
      <blockquote className="mt-3 border-l-2 border-slate-300 pl-3 text-sm italic text-slate-500">
        “{decision.source_quote}”
      </blockquote>
    </article>
  );
}
