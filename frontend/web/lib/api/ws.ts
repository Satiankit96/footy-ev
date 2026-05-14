import { useEffect, useRef, useState, useCallback } from "react";

function getSessionCookie(): string | null {
  const match = document.cookie.match(/(?:^|;\s*)session=([^;]*)/);
  return match ? match[1] : null;
}

const WS_BASE = "ws://localhost:8000";
const MAX_BACKOFF = 30_000;

export function useWebSocket<T>(
  path: string,
  options?: {
    enabled?: boolean;
    onMessage?: (data: T) => void;
  },
): {
  connected: boolean;
  lastMessage: T | null;
} {
  const [connected, setConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<T | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const mountedRef = useRef(true);
  const onMessageRef = useRef(options?.onMessage);

  const enabled = options?.enabled ?? true;

  useEffect(() => {
    onMessageRef.current = options?.onMessage;
  });

  const connect = useCallback(() => {
    if (!mountedRef.current || !enabled) return;

    const token = getSessionCookie();
    if (!token) return;

    const url = `${WS_BASE}${path}?token=${encodeURIComponent(token)}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) return;
      setConnected(true);
      retriesRef.current = 0;
    };

    ws.onmessage = (event: MessageEvent) => {
      if (!mountedRef.current) return;
      try {
        const data = JSON.parse(event.data as string) as T;
        setLastMessage(data);
        onMessageRef.current?.(data);
      } catch {
        // ignore unparseable messages
      }
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      setConnected(false);
      wsRef.current = null;
      const delay = Math.min(1000 * 2 ** retriesRef.current, MAX_BACKOFF);
      retriesRef.current += 1;
      setTimeout(() => {
        if (mountedRef.current && enabled) {
          // reconnect on next tick via effect re-run
          setConnected((prev) => prev);
        }
      }, delay);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [path, enabled]);

  useEffect(() => {
    mountedRef.current = true;
    if (enabled) connect();

    return () => {
      mountedRef.current = false;
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect, enabled]);

  return { connected, lastMessage };
}
