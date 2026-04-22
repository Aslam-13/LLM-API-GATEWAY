const STORAGE_KEY = "llm-gw-admin-key";

export function getToken(): string | null {
  return localStorage.getItem(STORAGE_KEY);
}

export function setToken(value: string) {
  localStorage.setItem(STORAGE_KEY, value);
}

export function clearToken() {
  localStorage.removeItem(STORAGE_KEY);
}

export function isAuthed(): boolean {
  return Boolean(getToken());
}
