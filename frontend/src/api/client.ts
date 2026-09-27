/**
 * Thin fetch wrapper for the real backend on 127.0.0.1:38210. `credentials:
 * "include"` on every request is the whole authentication story here --
 * auth is the httpOnly session cookie Module 01's backend already sets on
 * `/auth/login`, not a bearer token this client would otherwise have to
 * store and attach itself. The backend is genuinely cross-origin from the
 * Vite dev server (5173 vs 38210), so this only works because
 * `CORS_ORIGINS` on the backend explicitly allows this dev origin with
 * `allow_credentials=True` -- no dev-server proxy stands in for CORS here.
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:38210";

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

/** Extracts FastAPI's own error message shape (`{"detail": "..."}`) so the
 * UI can surface the real backend text verbatim rather than a generic
 * frontend message -- e.g. "invalid email or password", "invalid TOTP
 * code", exactly as the backend phrased it.
 */
function extractDetail(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      // FastAPI validation errors: list of {loc, msg, type}.
      const msgs = detail
        .map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : null))
        .filter((m): m is string => Boolean(m));
      if (msgs.length > 0) return msgs.join("; ");
    }
  }
  return fallback;
}

async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const isFormData = init?.body instanceof FormData;
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      // A FormData body must NOT get an explicit Content-Type here --
      // fetch/the browser sets `multipart/form-data; boundary=...` itself
      // once it serializes the FormData, and the boundary value is only
      // known at that point. Setting Content-Type manually (even to the
      // same-looking "multipart/form-data" string) omits or mismatches
      // the boundary and silently corrupts the body on the wire -- the
      // backend then can't parse the parts at all. JSON bodies still get
      // their own explicit header exactly as before.
      ...(init?.body && !isFormData ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });

  if (res.status === 204) {
    return undefined as T;
  }

  const text = await res.text();
  const body = text ? JSON.parse(text) : null;

  if (!res.ok) {
    throw new ApiError(res.status, extractDetail(body, `request failed (${res.status})`), body);
  }

  return body as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body !== undefined ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body !== undefined ? JSON.stringify(body) : undefined }),
  /** `DELETE` with a JSON body (Module 20's own `DELETE /notifications/
   * subscribe` -- the browser's own `PushSubscription.endpoint`, not a
   * server-side row id, is the only handle the frontend has to identify
   * which subscription to remove, so it travels in the body the same
   * way `post`'s own JSON body does).
   */
  delete: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "DELETE", body: body !== undefined ? JSON.stringify(body) : undefined }),
  /** For multipart/form-data uploads (e.g. `POST /import/applicants`) --
   * distinct from `post` because the body is a `FormData` instance passed
   * through as-is, never `JSON.stringify`'d, and never given an explicit
   * Content-Type (see `request`'s own comment above for why).
   */
  postFormData: <T>(path: string, formData: FormData) =>
    request<T>(path, { method: "POST", body: formData }),
};

export { API_BASE_URL };
