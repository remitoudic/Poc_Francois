import { httpApi } from './http';
import type { Api } from './types';

// VITE_API_MODE=http uses the real backend; anything else uses the in-memory mock
// until the v2 endpoints exist (backend plan, phase 5).
const mode = import.meta.env.VITE_API_MODE === 'http' ? 'http' : 'mock';

export const api: Api = mode === 'http' ? httpApi : (await import('./mock/engine')).mockApi;

export * from './types';
export { getActor, setActor } from './actor';
