'use client';

import { useEffect, useMemo, useState } from 'react';

import type { ActionItem } from '@/lib/meeting-detail';

/**
 * DispatchModal — approval UI for firing action items at Linear or
 * drafting a Gmail follow-up.
 *
 * Invariants:
 * 1. No external call fires on render. The user must click the submit
 *    button to trigger a network request.
 * 2. Per-item checkboxes let the user deselect anything before sending.
 * 3. On success, the response surfaces inline (Linear tickets as links,
 *    Gmail draft as a single edit URL).
 *
 * The modal is a shared shell used by both dispatch targets; the only
 * branches are the extra fields (team id vs. recipients) and the
 * success UI.
 */

export type DispatchMode = 'linear' | 'gmail';

interface DispatchModalProps {
  mode: DispatchMode;
  meetingId: string;
  actionItems: ActionItem[];
  isOpen: boolean;
  onClose: () => void;
}

interface LinearCreated {
  action_item_id: string;
  identifier: string;
  url: string;
}

interface LinearError {
  action_item_id: string | null;
  message: string;
}

interface LinearResponse {
  created: LinearCreated[];
  errors: LinearError[];
}

interface GmailResponse {
  draft_id: string;
  draft_url: string;
}

type Result =
  | { mode: 'linear'; payload: LinearResponse }
  | { mode: 'gmail'; payload: GmailResponse };

export function DispatchModal({
  mode,
  meetingId,
  actionItems,
  isOpen,
  onClose,
}: DispatchModalProps): JSX.Element | null {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(
    () => new Set(actionItems.map((i) => i.id)),
  );
  const [teamId, setTeamId] = useState('');
  const [recipientsRaw, setRecipientsRaw] = useState('');
  const [subject, setSubject] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Result | null>(null);

  // Reset modal state whenever it reopens — stale results from a prior
  // dispatch shouldn't leak into the next one.
  useEffect(() => {
    if (!isOpen) return;
    setSelectedIds(new Set(actionItems.map((i) => i.id)));
    setTeamId('');
    setRecipientsRaw('');
    setSubject('');
    setError(null);
    setResult(null);
  }, [isOpen, actionItems]);

  const selectedCount = selectedIds.size;

  const recipients = useMemo(
    () =>
      recipientsRaw
        .split(',')
        .map((r) => r.trim())
        .filter((r) => r.length > 0),
    [recipientsRaw],
  );

  const canSubmit = useMemo(() => {
    if (submitting || selectedCount === 0) return false;
    if (mode === 'linear') return teamId.trim().length > 0;
    return recipients.length > 0;
  }, [submitting, selectedCount, mode, teamId, recipients.length]);

  const toggle = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const body =
        mode === 'linear'
          ? {
              team_id: teamId.trim(),
              action_item_ids: actionItems
                .filter((i) => selectedIds.has(i.id))
                .map((i) => i.id),
            }
          : {
              recipients,
              subject: subject.trim() || undefined,
              action_item_ids: actionItems
                .filter((i) => selectedIds.has(i.id))
                .map((i) => i.id),
            };
      const res = await fetch(`/api/meetings/${meetingId}/dispatch/${mode}`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const detail = await res
          .json()
          .then((j) => (typeof j.detail === 'string' ? j.detail : null))
          .catch(() => null);
        setError(detail ?? `Request failed (HTTP ${res.status})`);
        return;
      }
      const json = await res.json();
      setResult(
        mode === 'linear'
          ? { mode: 'linear', payload: json as LinearResponse }
          : { mode: 'gmail', payload: json as GmailResponse },
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Network error');
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  const title =
    mode === 'linear' ? 'Create Linear tickets' : 'Draft Gmail follow-up';
  const submitLabel =
    mode === 'linear'
      ? `Create ${selectedCount} Linear ticket${selectedCount === 1 ? '' : 's'}`
      : 'Create draft';

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="dispatch-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
    >
      <div className="w-full max-w-lg rounded-lg bg-white p-5 shadow-xl">
        <header className="flex items-start justify-between">
          <h2 id="dispatch-modal-title" className="text-base font-semibold">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close dispatch modal"
            className="text-slate-400 hover:text-slate-600"
          >
            ×
          </button>
        </header>

        {result !== null ? (
          <ResultPanel result={result} onClose={onClose} />
        ) : (
          <>
            <p className="mt-3 text-xs text-slate-500">
              Review what will be sent. Uncheck items you don&apos;t want to
              include.
            </p>

            <ul className="mt-3 max-h-56 space-y-1 overflow-auto rounded border border-slate-200 p-2">
              {actionItems.map((item) => (
                <li key={item.id} className="flex items-start gap-2 text-sm">
                  <input
                    id={`dispatch-item-${item.id}`}
                    type="checkbox"
                    checked={selectedIds.has(item.id)}
                    onChange={() => toggle(item.id)}
                    className="mt-0.5"
                  />
                  <label
                    htmlFor={`dispatch-item-${item.id}`}
                    className="flex-1 cursor-pointer"
                  >
                    <span className="font-medium">{item.title}</span>
                    {(item.owner || item.due_date) && (
                      <span className="ml-2 text-xs text-slate-500">
                        {item.owner}
                        {item.owner && item.due_date ? ' • ' : ''}
                        {item.due_date}
                      </span>
                    )}
                  </label>
                </li>
              ))}
            </ul>

            {mode === 'linear' ? (
              <div className="mt-3">
                <label
                  htmlFor="dispatch-team-id"
                  className="block text-xs font-medium text-slate-600"
                >
                  Team ID
                </label>
                <input
                  id="dispatch-team-id"
                  type="text"
                  value={teamId}
                  onChange={(e) => setTeamId(e.target.value)}
                  placeholder="Linear team UUID"
                  className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
                />
              </div>
            ) : (
              <div className="mt-3 space-y-3">
                <div>
                  <label
                    htmlFor="dispatch-recipients"
                    className="block text-xs font-medium text-slate-600"
                  >
                    Recipients
                  </label>
                  <input
                    id="dispatch-recipients"
                    type="text"
                    value={recipientsRaw}
                    onChange={(e) => setRecipientsRaw(e.target.value)}
                    placeholder="comma-separated emails"
                    className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
                  />
                </div>
                <div>
                  <label
                    htmlFor="dispatch-subject"
                    className="block text-xs font-medium text-slate-600"
                  >
                    Subject (optional)
                  </label>
                  <input
                    id="dispatch-subject"
                    type="text"
                    value={subject}
                    onChange={(e) => setSubject(e.target.value)}
                    placeholder="Follow-up: <meeting title>"
                    className="mt-1 w-full rounded border border-slate-300 px-2 py-1 text-sm"
                  />
                </div>
              </div>
            )}

            {error !== null && (
              <p
                role="alert"
                className="mt-3 rounded bg-rose-50 p-2 text-sm text-rose-800"
              >
                {error}
              </p>
            )}

            <footer className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded border border-slate-300 px-3 py-1 text-sm"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={submit}
                disabled={!canSubmit}
                className="rounded bg-slate-900 px-3 py-1 text-sm text-white disabled:opacity-50"
              >
                {submitting ? 'Sending…' : submitLabel}
              </button>
            </footer>
          </>
        )}
      </div>
    </div>
  );
}

function ResultPanel({
  result,
  onClose,
}: {
  result: Result;
  onClose: () => void;
}): JSX.Element {
  if (result.mode === 'linear') {
    const { created, errors } = result.payload;
    return (
      <div className="mt-3 space-y-3 text-sm">
        {created.length > 0 && (
          <div>
            <p className="font-medium">Created tickets</p>
            <ul className="mt-1 space-y-1">
              {created.map((c) => (
                <li key={c.action_item_id}>
                  <a
                    href={c.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-blue-700 underline"
                  >
                    {c.identifier}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        )}
        {errors.length > 0 && (
          <div>
            <p className="font-medium text-rose-700">Failed</p>
            <ul className="mt-1 space-y-1 text-rose-700">
              {errors.map((e, idx) => (
                <li key={`${e.action_item_id ?? 'x'}-${idx}`}>{e.message}</li>
              ))}
            </ul>
          </div>
        )}
        <div className="flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded bg-slate-900 px-3 py-1 text-sm text-white"
          >
            Close
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="mt-3 space-y-3 text-sm">
      <p>
        Draft created in Gmail.{' '}
        <a
          href={result.payload.draft_url}
          target="_blank"
          rel="noreferrer"
          className="text-blue-700 underline"
        >
          Open draft in Gmail
        </a>
      </p>
      <div className="flex justify-end">
        <button
          type="button"
          onClick={onClose}
          className="rounded bg-slate-900 px-3 py-1 text-sm text-white"
        >
          Close
        </button>
      </div>
    </div>
  );
}
