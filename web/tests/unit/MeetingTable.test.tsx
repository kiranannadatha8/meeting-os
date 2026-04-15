import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

import { MeetingTable } from '@/components/MeetingTable';

const meeting = (overrides: Partial<{
  id: string;
  title: string;
  status: string;
  source_type: string;
  created_at: string;
}> = {}) => ({
  id: 'm-1',
  title: 'Sync',
  status: 'queued',
  source_type: 'text',
  created_at: '2026-04-14T22:00:00Z',
  ...overrides,
});

const fetchMock = vi.fn();
const originalFetch = global.fetch;

beforeEach(() => {
  fetchMock.mockReset();
  global.fetch = fetchMock as unknown as typeof global.fetch;
});

afterEach(() => {
  vi.useRealTimers();
  global.fetch = originalFetch;
  cleanup();
});

const okResponse = (body: unknown): Response =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });

describe('MeetingTable', () => {
  it('renders a row per meeting with title and status badge', async () => {
    fetchMock.mockResolvedValue(
      okResponse([
        meeting({ id: 'a', title: 'Q1 review', status: 'complete' }),
        meeting({ id: 'b', title: 'Sync', status: 'processing' }),
      ]),
    );

    render(<MeetingTable />);

    expect(await screen.findByText('Q1 review')).toBeInTheDocument();
    expect(screen.getByText('Sync')).toBeInTheDocument();
    expect(screen.getByText('complete')).toBeInTheDocument();
    expect(screen.getByText('processing')).toBeInTheDocument();
  });

  it('shows an empty state when no meetings exist', async () => {
    fetchMock.mockResolvedValue(okResponse([]));

    render(<MeetingTable />);

    expect(await screen.findByText(/no meetings yet/i)).toBeInTheDocument();
  });

  it('polls every 3s', async () => {
    fetchMock.mockResolvedValue(okResponse([]));
    vi.useFakeTimers({ shouldAdvanceTime: true });

    render(<MeetingTable />);
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('reflects status changes between polls', async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse([meeting({ id: 'x', title: 'Standup', status: 'queued' })]),
    );
    fetchMock.mockResolvedValueOnce(
      okResponse([meeting({ id: 'x', title: 'Standup', status: 'complete' })]),
    );
    vi.useFakeTimers({ shouldAdvanceTime: true });

    render(<MeetingTable />);
    expect(await screen.findByText('queued')).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });

    await vi.waitFor(() => expect(screen.getByText('complete')).toBeInTheDocument());
    expect(screen.queryByText('queued')).not.toBeInTheDocument();
  });
});
