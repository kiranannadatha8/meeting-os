import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

import { MeetingDetail } from '@/components/MeetingDetail';
import type { MeetingDetail as MeetingDetailPayload } from '@/lib/meeting-detail';

const fetchMock = vi.fn();
const originalFetch = global.fetch;

const okResponse = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });

const baseMeeting: MeetingDetailPayload = {
  id: 'm-1',
  title: 'Quarterly planning',
  status: 'complete',
  source_type: 'text',
  source_filename: 'plan.txt',
  transcript: 'we will ship on friday',
  error_message: null,
  created_at: '2026-04-14T10:00:00Z',
  updated_at: '2026-04-14T10:05:00Z',
  decisions: [
    {
      id: 'd-1',
      title: 'Adopt pgvector',
      rationale: 'fits our scale',
      source_quote: "we'll adopt pgvector",
    },
  ],
  action_items: [
    {
      id: 'a-1',
      title: 'Write ADR',
      owner: 'kiran',
      due_date: '2026-05-01',
      source_quote: 'kiran will write the ADR',
    },
  ],
  summary: {
    tldr: 'Team decided to adopt pgvector',
    highlights: ['Adopt pgvector', 'Ship on Friday', 'Write the ADR'],
  },
  langsmith_run_ids: ['run-a'],
};

beforeEach(() => {
  fetchMock.mockReset();
  global.fetch = fetchMock as unknown as typeof global.fetch;
});

afterEach(() => {
  vi.useRealTimers();
  global.fetch = originalFetch;
  cleanup();
});

describe('MeetingDetail — complete', () => {
  it('renders decisions, action items, and summary sections', async () => {
    fetchMock.mockResolvedValue(okResponse(baseMeeting));

    render(<MeetingDetail meetingId="m-1" />);

    expect(await screen.findByRole('heading', { name: 'Adopt pgvector' })).toBeInTheDocument();
    expect(screen.getByText('Write ADR')).toBeInTheDocument();
    expect(screen.getByText(/team decided to adopt pgvector/i)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /decisions/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /action items/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /summary/i })).toBeInTheDocument();
  });
});

describe('MeetingDetail — dispatch buttons', () => {
  it('renders Linear and Gmail dispatch buttons when status is complete', async () => {
    fetchMock.mockResolvedValue(okResponse(baseMeeting));

    render(<MeetingDetail meetingId="m-1" />);

    expect(
      await screen.findByRole('button', { name: /create linear tickets/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /draft gmail follow-up/i }),
    ).toBeInTheDocument();
  });

  it('opens the Linear dispatch modal on click', async () => {
    fetchMock.mockResolvedValue(okResponse(baseMeeting));

    render(<MeetingDetail meetingId="m-1" />);
    const button = await screen.findByRole('button', {
      name: /create linear tickets/i,
    });
    fireEvent.click(button);
    // Dialog renders with the Linear-specific Team ID input
    expect(
      screen.getByRole('dialog', { name: /create linear tickets/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/team id/i)).toBeInTheDocument();
  });

  it('hides dispatch buttons when the meeting is still processing', async () => {
    fetchMock.mockResolvedValue(
      okResponse({ ...baseMeeting, status: 'processing' }),
    );

    render(<MeetingDetail meetingId="m-1" />);

    await screen.findAllByTestId('agent-skeleton');
    expect(
      screen.queryByRole('button', { name: /create linear tickets/i }),
    ).not.toBeInTheDocument();
  });
});

describe('MeetingDetail — processing', () => {
  it('shows skeleton loaders for each section', async () => {
    fetchMock.mockResolvedValue(okResponse({ ...baseMeeting, status: 'processing' }));

    render(<MeetingDetail meetingId="m-1" />);

    const skeletons = await screen.findAllByTestId('agent-skeleton');
    expect(skeletons.length).toBeGreaterThanOrEqual(3);
  });
});

describe('MeetingDetail — failed', () => {
  it('shows the error message and a retry button', async () => {
    fetchMock.mockResolvedValue(
      okResponse({
        ...baseMeeting,
        status: 'failed',
        error_message: 'agents went sideways',
        decisions: [],
        action_items: [],
        summary: null,
      }),
    );

    render(<MeetingDetail meetingId="m-1" />);

    expect(await screen.findByText(/agents went sideways/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });

  it('calls the retry endpoint when the retry button is clicked', async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse({
        ...baseMeeting,
        status: 'failed',
        error_message: 'boom',
        decisions: [],
        action_items: [],
        summary: null,
      }),
    );
    fetchMock.mockResolvedValueOnce(okResponse({ id: 'm-1', status: 'queued' }, 202));
    fetchMock.mockResolvedValue(okResponse({ ...baseMeeting, status: 'queued' }));

    render(<MeetingDetail meetingId="m-1" />);
    const button = await screen.findByRole('button', { name: /retry/i });

    await act(async () => {
      fireEvent.click(button);
    });

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/meetings/m-1/retry',
        expect.objectContaining({ method: 'POST' }),
      ),
    );
  });
});
