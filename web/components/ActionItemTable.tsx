import type { ActionItem } from '@/lib/meeting-detail';

interface ActionItemTableProps {
  items: ActionItem[];
}

export function ActionItemTable({ items }: ActionItemTableProps): JSX.Element {
  if (items.length === 0) {
    return <p className="text-sm text-slate-500">No action items.</p>;
  }
  return (
    <table className="min-w-full divide-y divide-slate-200 text-sm">
      <thead>
        <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
          <th className="py-2 pr-4">Task</th>
          <th className="py-2 pr-4">Owner</th>
          <th className="py-2 pr-4">Due</th>
          <th className="py-2">Source</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-100">
        {items.map((item) => (
          <tr key={item.id} className="align-top">
            <td className="py-2 pr-4 font-medium">{item.title}</td>
            <td className="py-2 pr-4 text-slate-600">{item.owner ?? '—'}</td>
            <td className="py-2 pr-4 text-slate-600">{item.due_date ?? '—'}</td>
            <td className="py-2 text-slate-500 italic">“{item.source_quote}”</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
