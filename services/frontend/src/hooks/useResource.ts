import { useCallback, useEffect, useRef, useState } from 'react';

interface Resource<T> {
  data: T | undefined;
  error: Error | undefined;
  loading: boolean;
  /** Refetch without clearing the current data (no flicker on live updates). */
  reload: () => void;
}

export function useResource<T>(load: () => Promise<T>, deps: unknown[]): Resource<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<Error>();
  const [loading, setLoading] = useState(true);
  const seq = useRef(0);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(load, deps);

  const reload = useCallback(() => {
    const id = ++seq.current;
    run()
      .then((value) => {
        if (id === seq.current) {
          setData(value);
          setError(undefined);
        }
      })
      .catch((err: Error) => id === seq.current && setError(err))
      .finally(() => id === seq.current && setLoading(false));
  }, [run]);

  useEffect(() => {
    setLoading(true);
    reload();
  }, [reload]);

  return { data, error, loading, reload };
}
