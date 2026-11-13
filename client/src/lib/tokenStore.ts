/**
 * Single source of truth for the MindGuard access token.
 *
 * Policy: the access token is tab-scoped (sessionStorage) — it survives an
 * in-tab reload but dies with the tab. It never touches localStorage, so a
 * shared device holds nothing after the browser closes. "Keep me signed in"
 * is opt-in and lives server-side in an HttpOnly refresh cookie instead
 * (see POST /api/auth/refresh and docs/DATA_LIFECYCLE.md).
 */

const TOKEN_KEY = "mg_token";

export function getAccessToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setAccessToken(token: string): void {
  try {
    sessionStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* storage unavailable (private mode): session simply won't persist */
  }
}

export function clearAccessToken(): void {
  try {
    sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* nothing to do */
  }
}

/** Removes the token left behind by older builds that used localStorage. */
export function clearLegacyToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* nothing to do */
  }
}
