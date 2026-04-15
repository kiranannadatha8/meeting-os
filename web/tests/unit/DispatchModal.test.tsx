import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';

import { DispatchModal } from '@/components/DispatchModal';
import type { ActionItem } from '@/lib/meeting-detail';

const fetchMock = vi.fn();
const originalFetch = global.fetch;

const okResponse = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });

const items: ActionItem[] = [
  {
    id: 'a-1',
    title: 'Write migration',
    owner: 'Kiran',
    due_date: null,
    source_quote: "let's write it",
  },
  {
    id: 'a-2',
    title: 'Send recap',
    owner: null,
    due_date: '2026-05-01',
    source_quote: 'someone will send a recap',
  },
];

beforeEach(() => {
  fetchMock.mockReset();
  global.fetch = fetchMock as unknown as typeof global.fetch;
});

afterEach(() => {
  global.fetch = originalFetch;
  cleanup();
});

describe('DispatchModal — Linear mode', () => {
  it('renders per-item checkboxes that are all checked by default', () => {
    render(
      <DispatchModal
        mode="linear"
        meetingId="m-1"
        actionItems={items}
        isOpen
        onClose={() => {}}
      />,
    );
    const checkboxes = screen.getAllByRole('checkbox');
    expect(checkboxes).toHaveLength(2);
    expect(checkboxes.every((c) => (c as HTMLInputElement).checked)).toBe(true);
    expect(screen.getByText('Write migration')).toBeInTheDocument();
    expect(screen.getByText('Send recap')).toBeInTheDocument();
  });

  it('does not fire a network call until the user clicks Create', () => {
    render(
      <DispatchModal
        mode="linear"
        meetingId="m-1"
        actionItems={items}
        isOpen
        onClose={() => {}}
      />,
    );
    // User toggles checkboxes, types team id — still no fetch
    fireEvent.click(screen.getAllByRole('checkbox')[0]);
    fireEvent.change(screen.getByLabelText(/team id/i), {
      target: { value: 'team-uuid' },
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('posts only the checked items when the user confirms', async () => {
    fetchMock.mockResolvedValue(
      okResponse({
        created: [
          { action_item_id: 'a-2', identifier: 'ENG-2', url: 'https://linear.app/2' },
        ],
        errors: [],
      }),
    );

    render(
      <DispatchModal
        mode="linear"
        meetingId="m-1"
        actionItems={items}
        isOpen
        onClose={() => {}}
      />,
    );

    // Deselect the first item
    fireEvent.click(screen.getAllByRole('checkbox')[0]);
    fireEvent.change(screen.getByLabelText(/team id/i), {
      target: { value: 'team-uuid' },
    });

    await act(async () => {
      fireEvent.click(
        screen.getByRole('button', { name: /create 1 linear ticket/i }),
      );
    });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const call = fetchMock.mock.calls[0];
    expect(call[0]).toBe('/api/meetings/m-1/dispatch/linear');
    expect(call[1]?.method).toBe('POST');
    const body = JSON.parse(call[1]?.body as string);
    expect(body.team_id).toBe('team-uuid');
    expect(body.action_item_ids).toEqual(['a-2']);

    // Result URL surfaces inline
    expect(await screen.findByRole('link', { name: /ENG-2/i })).toHaveAttribute(
      'href',
      'https://linear.app/2',
    );
  });

  it('shows an error banner when the server returns 409', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Linear not configured' }), {
        status: 409,
        headers: { 'content-type': 'application/json' },
      }),
    );
    render(
      <DispatchModal
        mode="linear"
        meetingId="m-1"
        actionItems={items}
        isOpen
        onClose={() => {}}
      />,
    );
    fireEvent.change(screen.getByLabelText(/team id/i), {
      target: { value: 't' },
    });
    await act(async () => {
      fireEvent.click(
        screen.getByRole('button', { name: /create 2 linear tickets/i }),
      );
    });
    expect(
      await screen.findByText(/linear not configured/i),
    ).toBeInTheDocument();
  });

  it('disables the submit button when nothing is selected', () => {
    render(
      <DispatchModal
        mode="linear"
        meetingId="m-1"
        actionItems={items}
        isOpen
        onClose={() => {}}
      />,
    );
    fireEvent.click(screen.getAllByRole('checkbox')[0]);
    fireEvent.click(screen.getAllByRole('checkbox')[1]);
    const submit = screen.getByRole('button', { name: /create/i });
    expect(submit).toBeDisabled();
  });
});

describe('DispatchModal — Gmail mode', () => {
  it('collects recipients and posts a draft on confirm', async () => {
    fetchMock.mockResolvedValue(
      okResponse({
        draft_id: 'd1',
        draft_url: 'https://mail.google.com/mail/u/0/#drafts?compose=m1',
      }),
    );

    render(
      <DispatchModal
        mode="gmail"
        meetingId="m-1"
        actionItems={items}
        isOpen
        onClose={() => {}}
      />,
    );

    fireEvent.change(screen.getByLabelText(/recipients/i), {
      target: { value: 'team@example.com, kiran@example.com' },
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /create draft/i }));
    });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const call = fetchMock.mock.calls[0];
    expect(call[0]).toBe('/api/meetings/m-1/dispatch/gmail');
    const body = JSON.parse(call[1]?.body as string);
    expect(body.recipients).toEqual(['team@example.com', 'kiran@example.com']);
    expect(body.action_item_ids).toEqual(['a-1', 'a-2']);

    expect(
      await screen.findByRole('link', { name: /open draft in gmail/i }),
    ).toHaveAttribute(
      'href',
      'https://mail.google.com/mail/u/0/#drafts?compose=m1',
    );
  });

  it('disables submit until at least one recipient is entered', () => {
    render(
      <DispatchModal
        mode="gmail"
        meetingId="m-1"
        actionItems={items}
        isOpen
        onClose={() => {}}
      />,
    );
    const submit = screen.getByRole('button', { name: /create draft/i });
    expect(submit).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/recipients/i), {
      target: { value: 'a@b.com' },
    });
    expect(submit).not.toBeDisabled();
  });
});

describe('DispatchModal — isOpen=false', () => {
  it('renders nothing when closed', () => {
    const { container } = render(
      <DispatchModal
        mode="linear"
        meetingId="m-1"
        actionItems={items}
        isOpen={false}
        onClose={() => {}}
      />,
    );
    expect(container.firstChild).toBeNull();
  });
});
