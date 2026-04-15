import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

import { SearchPanel } from '@/components/SearchPanel';

const fetchMock = vi.fn();
const originalFetch = global.fetch;

const okResponse = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });

beforeEach(() => {
  fetchMock.mockReset();
  global.fetch = fetchMock as unknown as typeof global.fetch;
});

afterEach(() => {
  global.fetch = originalFetch;
  cleanup();
});

describe('SearchPanel', () => {
  it('submits the query to /api/search on submit', async () => {
    fetchMock.mockResolvedValue(okResponse({ results: [] }));

    render(<SearchPanel />);

    fireEvent.change(screen.getByLabelText(/search/i), {
      target: { value: 'pricing model' },
    });
    await act(async () => {
      fireEvent.submit(screen.getByRole('search'));
    });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/search?q=pricing+model');
  });

  it('does not fire a network call on initial render', () => {
    render(<SearchPanel />);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('renders results with meeting title, snippet, and highlighted terms', async () => {
    fetchMock.mockResolvedValue(
      okResponse({
        results: [
          {
            meeting_id: 'm-1',
            meeting_title: 'Pricing sync',
            meeting_created_at: '2026-04-14T10:00:00Z',
            chunk_content: 'we raised pricing by 10 percent last quarter',
            distance: 0.11,
          },
        ],
      }),
    );

    render(<SearchPanel />);
    fireEvent.change(screen.getByLabelText(/search/i), {
      target: { value: 'pricing' },
    });
    await act(async () => {
      fireEvent.submit(screen.getByRole('search'));
    });

    expect(await screen.findByText('Pricing sync')).toBeInTheDocument();
    // The matching term is highlighted (rendered inside a <mark>)
    const marks = await screen.findAllByText('pricing', { selector: 'mark' });
    expect(marks.length).toBeGreaterThanOrEqual(1);
    // Meeting result links to its detail page
    const link = screen.getByRole('link', { name: /pricing sync/i });
    expect(link).toHaveAttribute('href', '/meetings/m-1');
  });

  it('renders an empty-state message when there are no results', async () => {
    fetchMock.mockResolvedValue(okResponse({ results: [] }));

    render(<SearchPanel />);
    fireEvent.change(screen.getByLabelText(/search/i), {
      target: { value: 'no match' },
    });
    await act(async () => {
      fireEvent.submit(screen.getByRole('search'));
    });

    expect(await screen.findByText(/no results/i)).toBeInTheDocument();
  });

  it('surfaces an error banner when the upstream fails', async () => {
    fetchMock.mockResolvedValue(new Response('boom', { status: 500 }));

    render(<SearchPanel />);
    fireEvent.change(screen.getByLabelText(/search/i), {
      target: { value: 'pricing' },
    });
    await act(async () => {
      fireEvent.submit(screen.getByRole('search'));
    });

    expect(await screen.findByRole('alert')).toHaveTextContent(/failed/i);
  });

  it('ignores empty / whitespace-only queries', async () => {
    render(<SearchPanel />);
    fireEvent.change(screen.getByLabelText(/search/i), {
      target: { value: '   ' },
    });
    await act(async () => {
      fireEvent.submit(screen.getByRole('search'));
    });

    expect(fetchMock).not.toHaveBeenCalled();
  });
});
