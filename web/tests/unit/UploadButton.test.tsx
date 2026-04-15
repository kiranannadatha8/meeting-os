import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

import { UploadButton } from '@/components/UploadButton';

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

const fileInput = (container: HTMLElement): HTMLInputElement => {
  const el = container.querySelector('input[type="file"]');
  if (!el) throw new Error('no file input found');
  return el as HTMLInputElement;
};

describe('UploadButton', () => {
  it('renders a button labelled "Upload"', () => {
    render(<UploadButton onUploaded={() => {}} />);
    expect(screen.getByRole('button', { name: /upload/i })).toBeInTheDocument();
  });

  it('POSTs the selected file to /api/meetings and notifies the parent', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ id: 'm-77', status: 'queued' }), { status: 201 }),
    );
    const onUploaded = vi.fn();

    const { container } = render(<UploadButton onUploaded={onUploaded} />);
    const file = new File(['hi there'], 'notes.txt', { type: 'text/plain' });

    fireEvent.change(fileInput(container), { target: { files: [file] } });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/meetings');
    expect(init.method).toBe('POST');
    const body = init.body as FormData;
    expect(body.get('title')).toBe('notes.txt');
    expect(body.get('file')).toBeInstanceOf(File);

    await waitFor(() => expect(onUploaded).toHaveBeenCalledTimes(1));
  });

  it('shows an error message when the upload is rejected', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: 'unsupported' }), { status: 422 }),
    );
    const onUploaded = vi.fn();

    const { container } = render(<UploadButton onUploaded={onUploaded} />);
    fireEvent.change(fileInput(container), {
      target: { files: [new File(['x'], 'bad.pdf', { type: 'application/pdf' })] },
    });

    expect(await screen.findByText(/upload failed/i)).toBeInTheDocument();
    expect(onUploaded).not.toHaveBeenCalled();
  });
});
