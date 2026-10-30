// Who is acting, until sign-in exists: a name typed in the header, sent as `X-Fox-Actor`
// and written to the workflow logs.
const STORAGE_KEY = 'fox.actor';
const MAX_LENGTH = 100;

export function getActor(): string {
  return (localStorage.getItem(STORAGE_KEY) ?? '').trim();
}

export function setActor(name: string): void {
  const value = name.trim().slice(0, MAX_LENGTH);
  if (value) localStorage.setItem(STORAGE_KEY, value);
  else localStorage.removeItem(STORAGE_KEY);
}
