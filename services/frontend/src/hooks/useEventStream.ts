import { useEffect, useRef } from 'react';
import { api, type EventItem, type EventScope } from '../api';

/**
 * Subscribe to live events for a scope. `onChange` is debounced, so a burst of events
 * causes a single refetch. It also fires on `resync` (events may have been missed).
 */
export function useEventStream(
  scope: EventScope,
  onChange: () => void,
  onEvent?: (e: EventItem) => void,
  debounceMs = 300,
): void {
  const changeRef = useRef(onChange);
  const eventRef = useRef(onEvent);
  useEffect(() => {
    changeRef.current = onChange;
    eventRef.current = onEvent;
  });
  const { order_id, position_id } = scope;

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const schedule = () => {
      clearTimeout(timer);
      timer = setTimeout(() => changeRef.current(), debounceMs);
    };
    const unsubscribe = api.subscribe(
      { order_id, position_id },
      (e) => {
        eventRef.current?.(e);
        schedule();
      },
      schedule,
    );
    return () => {
      clearTimeout(timer);
      unsubscribe();
    };
  }, [order_id, position_id, debounceMs]);
}
