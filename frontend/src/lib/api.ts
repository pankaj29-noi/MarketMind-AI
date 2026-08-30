/**
 * Backend API base URL.
 * Override with VITE_API_BASE_URL in frontend/.env.local when the API
 * is not on the default port (e.g. http://127.0.0.1:8081).
 */
export const API_BASE =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ||
  "http://localhost:8000";
