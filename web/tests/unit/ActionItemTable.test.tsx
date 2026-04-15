import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

import { ActionItemTable } from '@/components/ActionItemTable';

afterEach(cleanup);

describe('ActionItemTable', () => {
  it('renders a row per action item with owner and due date', () => {
    render(
      <ActionItemTable
        items={[
          {
            id: 'a-1',
            title: 'Write ADR',
            owner: 'kiran',
            due_date: '2026-05-01',
            source_quote: 'kiran will write the ADR',
          },
          {
            id: 'a-2',
            title: 'Talk to legal',
            owner: null,
            due_date: null,
            source_quote: 'someone should loop in legal',
          },
        ]}
      />,
    );

    expect(screen.getByText('Write ADR')).toBeInTheDocument();
    expect(screen.getByText('kiran')).toBeInTheDocument();
    expect(screen.getByText('2026-05-01')).toBeInTheDocument();
    expect(screen.getByText('Talk to legal')).toBeInTheDocument();
    // Unassigned items render a dash rather than "null"
    expect(screen.queryByText('null')).not.toBeInTheDocument();
  });

  it('shows empty state when there are no items', () => {
    render(<ActionItemTable items={[]} />);
    expect(screen.getByText(/no action items/i)).toBeInTheDocument();
  });
});
