'use client';

import Link from 'next/link';
import { Fragment, useState } from 'react';

interface SearchResult {
  meeting_id: string;
  meeting_title: string;
  meeting_created_at: string;
  chunk_content: string;
  distance: number;
}

interface SearchResponse {
  results: SearchResult[];
}

function highlight(text: string, query: string): React.ReactNode {
  const trimmed = query.trim();
  if (!trimmed) return text;
  const pattern = new RegExp(
    `(${trimmed.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`,
    'ig',
  );
  const parts = text.split(pattern);
  return parts.map((part, i) =>
    pattern.test(part) ? (
      <mark key={i} className="rounded bg-amber-200 px-0.5">
        {part}
      </mark>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    ),
  );
}

export function SearchPanel(): JSX.Element {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastQuery, setLastQuery] = useState('');

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;

    setLoading(true);
    setError(null);
    setLastQuery(trimmed);

    try {
      const params = new URLSearchParams({ q: trimmed });
      const res = await fetch(`/api/search?${params.toString()}`, {
        cache: 'no-store',
      });
      if (!res.ok) {
        setResults(null);
        setError(`Search failed (HTTP ${res.status})`);
        return;
      }
      const data = (await res.json()) as SearchResponse;
      setResults(data.results);
    } catch {
      setResults(null);
      setError('Search failed — network error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <form role="search" onSubmit={onSubmit} className="flex gap-2">
        <label htmlFor="search-query" className="sr-only">
          Search meetings
        </label>
        <input
          id="search-query"
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search across meetings…"
          className="flex-1 rounded border border-slate-300 px-3 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={loading}
          className="rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-60"
        >
          {loading ? 'Searching…' : 'Search'}
        </button>
      </form>

      {error && (
        <p role="alert" className="rounded border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
          {error}
        </p>
      )}

      {results !== null && results.length === 0 && (
        <p className="text-sm text-slate-500">No results for &ldquo;{lastQuery}&rdquo;.</p>
      )}

      {results !== null && results.length > 0 && (
        <ul className="space-y-3">
          {results.map((r, idx) => (
            <li
              key={`${r.meeting_id}-${idx}`}
              className="rounded border border-slate-200 bg-white p-4"
            >
              <Link
                href={`/meetings/${r.meeting_id}`}
                className="text-sm font-semibold text-slate-900 hover:underline"
              >
                {r.meeting_title}
              </Link>
              <p className="mt-2 text-sm text-slate-700">
                {highlight(r.chunk_content, lastQuery)}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
