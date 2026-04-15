'use client';

import { useCallback, useEffect, useState } from 'react';

type Provider = 'linear' | 'gmail';

interface IntegrationStatus {
  linear: boolean;
  gmail: boolean;
}

type Feedback = { kind: 'idle' } | { kind: 'error'; message: string };

interface ProviderSectionProps {
  title: string;
  provider: Provider;
  connected: boolean;
  keyLabel: string;
  onSaved: () => void;
  onDisconnected: () => void;
  helpText?: string;
}

const DEFAULT_STATUS: IntegrationStatus = { linear: false, gmail: false };

function ProviderSection({
  title,
  provider,
  connected,
  keyLabel,
  onSaved,
  onDisconnected,
  helpText,
}: ProviderSectionProps) {
  const [value, setValue] = useState('');
  const [feedback, setFeedback] = useState<Feedback>({ kind: 'idle' });
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (!value) return;
    setBusy(true);
    try {
      const res = await fetch('/api/integrations', {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ provider, api_key: value }),
      });
      if (!res.ok) {
        setFeedback({ kind: 'error', message: `Save failed (${res.status})` });
        return;
      }
      setValue('');
      setFeedback({ kind: 'idle' });
      onSaved();
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    setBusy(true);
    try {
      const res = await fetch(`/api/integrations?provider=${provider}`, { method: 'DELETE' });
      if (!res.ok) {
        setFeedback({ kind: 'error', message: `Disconnect failed (${res.status})` });
        return;
      }
      setFeedback({ kind: 'idle' });
      onDisconnected();
    } finally {
      setBusy(false);
    }
  };

  const inputId = `integration-${provider}-key`;

  return (
    <section className="space-y-3 rounded border border-slate-200 bg-white p-4">
      <header className="flex items-center justify-between">
        <h2 className="text-base font-medium capitalize">{title}</h2>
        <span
          className={
            connected
              ? 'text-xs font-medium text-emerald-600'
              : 'text-xs font-medium text-slate-500'
          }
        >
          {connected ? `${title} connected` : `${title} not connected`}
        </span>
      </header>

      {helpText && <p className="text-xs text-slate-500">{helpText}</p>}

      <div className="space-y-2">
        <label htmlFor={inputId} className="block text-xs font-medium text-slate-700">
          {keyLabel}
        </label>
        <input
          id={inputId}
          type="password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          autoComplete="off"
          className="w-full rounded border border-slate-300 px-2 py-1 text-sm"
        />
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={save}
          disabled={busy || !value}
          className="rounded bg-slate-900 px-3 py-1 text-sm font-medium text-white disabled:opacity-60"
        >
          {`Save ${title}`}
        </button>
        {connected && (
          <button
            type="button"
            onClick={disconnect}
            disabled={busy}
            className="rounded border border-rose-300 px-3 py-1 text-sm text-rose-700 disabled:opacity-60"
          >
            {`Disconnect ${title}`}
          </button>
        )}
      </div>

      {feedback.kind === 'error' && (
        <p role="alert" className="text-sm text-rose-600">
          {feedback.message}
        </p>
      )}
    </section>
  );
}

export function SettingsPanel() {
  const [status, setStatus] = useState<IntegrationStatus>(DEFAULT_STATUS);

  const refresh = useCallback(async () => {
    const res = await fetch('/api/integrations', { cache: 'no-store' });
    if (res.ok) {
      const data = (await res.json()) as IntegrationStatus;
      setStatus(data);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <div className="space-y-4">
      <ProviderSection
        title="Linear"
        provider="linear"
        connected={status.linear}
        keyLabel="Linear API key"
        helpText="Generate a personal API key in Linear Settings → API."
        onSaved={refresh}
        onDisconnected={refresh}
      />
      <ProviderSection
        title="Gmail"
        provider="gmail"
        connected={status.gmail}
        keyLabel="Gmail OAuth refresh token"
        helpText="Paste a refresh token with gmail.compose scope (OAuth flow lands in a later milestone)."
        onSaved={refresh}
        onDisconnected={refresh}
      />
    </div>
  );
}
