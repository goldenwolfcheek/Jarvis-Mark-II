import { useState, useEffect, useRef, useCallback } from 'react';
import { WS_URL, WS_RECONNECT_DELAY, WS_MAX_RECONNECT_DELAY, WS_HEARTBEAT_INTERVAL } from '../utils/constants';

export default function useWebSocket(onMessage) {
  const [status, setStatus] = useState('disconnected');
  const [sessionId, setSessionId] = useState(null);
  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const heartbeatRef = useRef(null);
  const reconnectDelayRef = useRef(WS_RECONNECT_DELAY);
  const onMessageRef = useRef(onMessage);
  // Always keep the ref in sync with the latest callback
  useEffect(() => { onMessageRef.current = onMessage; }, [onMessage]);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setStatus('connecting');
    const ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      setStatus('connected');
      reconnectDelayRef.current = WS_RECONNECT_DELAY;

      // Start heartbeat
      heartbeatRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, WS_HEARTBEAT_INTERVAL);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        // Handle initial connected message
        if (data.type === 'connected' && data.session_id) {
          setSessionId(data.session_id);
        }

        // Pass to the message handler (always the latest)
        if (onMessageRef.current) onMessageRef.current(data);
      } catch (e) {
        console.warn('[WS] Failed to parse message:', e);
      }
    };

    ws.onclose = () => {
      // Stale WebSocket guard — if a new connect() replaced wsRef.current
      // (e.g. during StrictMode double-mount), ignore this stale event
      if (wsRef.current !== ws) return;

      setStatus('disconnected');
      if (heartbeatRef.current) {
        clearInterval(heartbeatRef.current);
        heartbeatRef.current = null;
      }
      wsRef.current = null;

      // Auto-reconnect with exponential backoff
      const delay = reconnectDelayRef.current;
      reconnectTimerRef.current = setTimeout(() => {
        reconnectDelayRef.current = Math.min(
          reconnectDelayRef.current * 1.5,
          WS_MAX_RECONNECT_DELAY
        );
        connect();
      }, delay);
    };

    ws.onerror = () => {
      // Stale guard — same as onclose
      if (wsRef.current !== ws) return;
      // onclose will fire after this, so no need to handle here
    };

    wsRef.current = ws;
  }, []); // No dependencies — onMessage accessed via ref

  const disconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (heartbeatRef.current) {
      clearInterval(heartbeatRef.current);
      heartbeatRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setStatus('disconnected');
    setSessionId(null);
  }, []);

  const sendMessage = useCallback((message) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
      return true;
    }
    return false;
  }, []);

  useEffect(() => {
    connect();
    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  return { status, sessionId, sendMessage, reconnect: connect, disconnect };
}
