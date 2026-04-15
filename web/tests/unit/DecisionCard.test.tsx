import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

import { DecisionCard } from '@/components/DecisionCard';

afterEach(cleanup);

describe('DecisionCard', () => {
  it('renders the title, rationale, and source quote', () => {
    render(
      <DecisionCard
        decision={{
          id: 'd-1',
          title: 'Adopt pgvector',
          rationale: 'Fits our scale and simplifies ops',
          source_quote: "we'll adopt pgvector for vector storage",
        }}
      />,
    );

    expect(screen.getByText('Adopt pgvector')).toBeInTheDocument();
    expect(screen.getByText(/fits our scale/i)).toBeInTheDocument();
    expect(screen.getByText(/we'll adopt pgvector/i)).toBeInTheDocument();
  });

  it('marks the source quote as a <blockquote> for accessibility', () => {
    const { container } = render(
      <DecisionCard
        decision={{
          id: 'd-2',
          title: 't',
          rationale: 'r',
          source_quote: 's',
        }}
      />,
    );
    expect(container.querySelector('blockquote')).not.toBeNull();
  });
});
