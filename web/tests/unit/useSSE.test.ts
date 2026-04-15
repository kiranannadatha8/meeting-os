/**
 * `useSSE` subscribes to the meeting's SSE endpoint and returns the
 * latest `status` payload. Caller passes `enabled=false` to skip the
 * subscription entirely — useful when the meeting is already terminal.
 *
 * jsdom doesn't ship an EventSource, so each test installs a fake on
 * `globalThis` before rendering.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, act, cleanup } from '@testing-library/react';

import { useSSE } from '@/lib/useSSE';

type Listener = (event: MessageEvent) => void;

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  url: string;
  closed = false;
  private listeners = new Map<string, Set<Listener>>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, fn: Listener): void {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)!.add(fn);
  }

  removeEventListener(type: string, fn: Listener): void {
    this.listeners.get(type)?.delete(fn);
  }

  close(): void {
    this.closed = true;
  }

  emit(type: string, data: unknown): void {
    const event = new MessageEvent(type, { data: JSON.stringify(data) });
    this.listeners.get(type)?.forEach((fn) => fn(event));
  }
}

beforeEach(() => {
  FakeEventSource.instances = [];
  (globalThis as unknown as { EventSource: typeof FakeEventSource }).EventSource =
    FakeEventSource;
});

afterEach(() => {
  delete (globalThis as unknown as { EventSource?: unknown }).EventSource;
  cleanup();
});

describe('useSSE', () => {
  it('subscribes to the meeting events endpoint and returns the latest status', () => {
    const { result } = renderHook(() => useSSE('m-1'));

    expect(FakeEventSource.instances).toHaveLength(1);
    expect(FakeEventSource.instances[0].url).toBe('/api/meetings/m-1/events');
    expect(result.current).toBeNull();

    act(() => {
      FakeEventSource.instances[0].emit('status', {
        status: 'processing',
        error_message: null,
      });
    });
    expect(result.current).toEqual({ status: 'processing', error_message: null });

    act(() => {
      FakeEventSource.instances[0].emit('status', {
        status: 'complete',
        error_message: null,
      });
    });
    expect(result.current).toEqual({ status: 'complete', error_message: null });
  });

  it('skips subscription when enabled is false', () => {
    renderHook(() => useSSE('m-1', { enabled: false }));
    expect(FakeEventSource.instances).toHaveLength(0);
  });

  it('closes the EventSource on unmount', () => {
    const { unmount } = renderHook(() => useSSE('m-1'));
    const src = FakeEventSource.instances[0];
    expect(src.closed).toBe(false);

    unmount();
    expect(src.closed).toBe(true);
  });

  it('ignores malformed payloads instead of crashing', () => {
    const { result } = renderHook(() => useSSE('m-1'));
    const src = FakeEventSource.instances[0];

    act(() => {
      // Simulate a non-JSON data frame
      const event = new MessageEvent('status', { data: 'not-json' });
      // @ts-expect-error poking the private map to bypass JSON.stringify
      src.listeners.get('status')?.forEach((fn) => fn(event));
    });
    expect(result.current).toBeNull();
  });
});
