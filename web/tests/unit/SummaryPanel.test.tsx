import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

import { SummaryPanel } from '@/components/SummaryPanel';

afterEach(cleanup);

describe('SummaryPanel', () => {
  it('renders the TL;DR and each highlight as a list item', () => {
    render(
      <SummaryPanel
        summary={{
          tldr: 'Team decided to adopt pgvector and ship on Friday',
          highlights: ['Adopt pgvector', 'Ship on Friday', 'Write the ADR'],
        }}
      />,
    );

    expect(screen.getByText(/team decided to adopt pgvector/i)).toBeInTheDocument();
    expect(screen.getAllByRole('listitem')).toHaveLength(3);
    expect(screen.getByText('Adopt pgvector')).toBeInTheDocument();
  });

  it('strips reference markers so [[decision:0]] does not leak into the UI', () => {
    render(
      <SummaryPanel
        summary={{
          tldr: 'We will adopt pgvector [[decision:0]]',
          highlights: ['Adopt pgvector [[decision:0]] [[action:1]]', 'Plain'],
        }}
      />,
    );

    // The raw marker text must not appear — the panel resolves or strips them.
    expect(screen.queryByText(/\[\[decision:0\]\]/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\[\[action:1\]\]/)).not.toBeInTheDocument();
    expect(screen.getByText(/we will adopt pgvector/i)).toBeInTheDocument();
  });

  it('renders an empty state when summary is null', () => {
    render(<SummaryPanel summary={null} />);
    expect(screen.getByText(/no summary yet/i)).toBeInTheDocument();
  });
});
