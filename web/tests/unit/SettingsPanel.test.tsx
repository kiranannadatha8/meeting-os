import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

import { SettingsPanel } from '@/components/SettingsPanel';

const fetchMock = vi.fn();
const originalFetch = global.fetch;

beforeEach(() => {
  fetchMock.mockReset();
  global.fetch = fetchMock as unknown as typeof global.fetch;
});

afterEach(() => {
  global.fetch = originalFetch;
  cleanup();
});

const statusResponse = (status: { linear: boolean; gmail: boolean }): Response =>
  new Response(JSON.stringify(status), { status: 200 });

describe('SettingsPanel', () => {
  it('renders a section per integration with current connection state', async () => {
    fetchMock.mockResolvedValueOnce(statusResponse({ linear: true, gmail: false }));

    render(<SettingsPanel />);

    expect(await screen.findByRole('heading', { name: /linear/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /gmail/i })).toBeInTheDocument();
    expect(screen.getByText(/linear connected/i)).toBeInTheDocument();
    expect(screen.getByText(/gmail not connected/i)).toBeInTheDocument();
  });

  it('saves a Linear API key via PUT and refreshes status', async () => {
    fetchMock
      .mockResolvedValueOnce(statusResponse({ linear: false, gmail: false }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ok' }), { status: 200 }))
      .mockResolvedValueOnce(statusResponse({ linear: true, gmail: false }));

    render(<SettingsPanel />);

    const input = await screen.findByLabelText(/linear api key/i);
    fireEvent.change(input, { target: { value: 'lin_api_xyz' } });
    fireEvent.click(screen.getByRole('button', { name: /save linear/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const [, putCall] = fetchMock.mock.calls;
    const [putUrl, putInit] = putCall;
    expect(putUrl).toBe('/api/integrations');
    expect(putInit.method).toBe('PUT');
    expect(JSON.parse(putInit.body as string)).toEqual({
      provider: 'linear',
      api_key: 'lin_api_xyz',
    });
    expect(await screen.findByText(/linear connected/i)).toBeInTheDocument();
  });

  it('disconnects a configured integration via DELETE', async () => {
    fetchMock
      .mockResolvedValueOnce(statusResponse({ linear: true, gmail: false }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(statusResponse({ linear: false, gmail: false }));

    render(<SettingsPanel />);

    const disconnectBtn = await screen.findByRole('button', { name: /disconnect linear/i });
    fireEvent.click(disconnectBtn);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const [, deleteCall] = fetchMock.mock.calls;
    const [delUrl, delInit] = deleteCall;
    expect(delUrl).toBe('/api/integrations?provider=linear');
    expect(delInit.method).toBe('DELETE');
    expect(await screen.findByText(/linear not connected/i)).toBeInTheDocument();
  });

  it('surfaces API failures without losing the form input', async () => {
    fetchMock
      .mockResolvedValueOnce(statusResponse({ linear: false, gmail: false }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'nope' }), { status: 422 }));

    render(<SettingsPanel />);

    const input = await screen.findByLabelText(/linear api key/i);
    fireEvent.change(input, { target: { value: 'bad' } });
    fireEvent.click(screen.getByRole('button', { name: /save linear/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/failed/i);
    expect((input as HTMLInputElement).value).toBe('bad');
  });
});
