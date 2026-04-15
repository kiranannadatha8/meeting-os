'use client';

import { useRef, useState } from 'react';

interface UploadButtonProps {
  onUploaded: () => void;
}

type UploadState = { kind: 'idle' } | { kind: 'uploading' } | { kind: 'error'; message: string };

const ACCEPTED = '.txt,.md,.mp3,.wav,text/plain,text/markdown,audio/mpeg,audio/wav';

export function UploadButton({ onUploaded }: UploadButtonProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [state, setState] = useState<UploadState>({ kind: 'idle' });

  const onClick = () => {
    inputRef.current?.click();
  };

  const onChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;

    setState({ kind: 'uploading' });
    const body = new FormData();
    body.append('title', file.name);
    body.append('file', file);

    try {
      const res = await fetch('/api/meetings', { method: 'POST', body });
      if (!res.ok) {
        setState({ kind: 'error', message: `Upload failed (${res.status})` });
        return;
      }
      setState({ kind: 'idle' });
      onUploaded();
    } catch {
      setState({ kind: 'error', message: 'Upload failed — network error' });
    }
  };

  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={onClick}
        disabled={state.kind === 'uploading'}
        className="rounded bg-slate-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60"
      >
        {state.kind === 'uploading' ? 'Uploading…' : 'Upload'}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED}
        onChange={onChange}
        className="sr-only"
      />
      {state.kind === 'error' && (
        <p role="alert" className="text-sm text-rose-600">
          {state.message}
        </p>
      )}
    </div>
  );
}
