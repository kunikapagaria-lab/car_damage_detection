'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { WS_URL } from '@/lib/api';
import { useStore } from '@/lib/store';
import type { WSMessage, WSInspectionFrame } from '@/types';

// ── WebSocket feed ────────────────────────────────────────────────────────────

export function useWebSocketFeed(): void {
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout>>();
  const setFrame = useStore((s) => s.setFrame);
  const addAlert = useStore((s) => s.addAlert);
  const setWsStatus = useStore((s) => s.setWsStatus);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setWsStatus('connecting');
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      setWsStatus('connected');
      clearTimeout(retryRef.current);
    };

    ws.onmessage = (ev: MessageEvent<string>) => {
      try {
        const msg = JSON.parse(ev.data) as WSMessage;
        if (msg.event === 'inspection_result') {
          const frame = msg as WSInspectionFrame;
          setFrame(frame);
          if (frame.n_damages > 0) addAlert(frame);
        }
      } catch {
        // malformed message — ignore
      }
    };

    ws.onclose = () => {
      setWsStatus('disconnected');
      retryRef.current = setTimeout(connect, 5_000);
    };

    ws.onerror = () => ws.close();
  }, [addAlert, setFrame, setWsStatus]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(retryRef.current);
      wsRef.current?.close();
    };
  }, [connect]);
}

// ── Debounce ──────────────────────────────────────────────────────────────────

export function useDebounce<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState<T>(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

// ── Clock ─────────────────────────────────────────────────────────────────────

export function useClock(): string {
  const [time, setTime] = useState<string>('');

  useEffect(() => {
    setTime(new Date().toLocaleTimeString('en-IN', { hour12: false }));
    const id = setInterval(
      () => setTime(new Date().toLocaleTimeString('en-IN', { hour12: false })),
      1_000
    );
    return () => clearInterval(id);
  }, []);

  return time;
}

// ── Intersection-observer lazy load ──────────────────────────────────────────

export function useInView(
  ref: React.RefObject<Element>,
  options?: IntersectionObserverInit
): boolean {
  const [inView, setInView] = useState(false);
  useEffect(() => {
    if (!ref.current) return;
    const obs = new IntersectionObserver(
      ([entry]) => setInView(entry.isIntersecting),
      options
    );
    obs.observe(ref.current);
    return () => obs.disconnect();
  }, [ref, options]);
  return inView;
}
