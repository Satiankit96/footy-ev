export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    public requestId: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  params?: Record<string, string>,
): Promise<T> {
  const requestId = crypto.randomUUID();

  let url = `${BASE_URL}${path}`;
  if (params) {
    const qs = new URLSearchParams(params).toString();
    url = `${url}?${qs}`;
  }

  const headers: Record<string, string> = {
    "X-Request-ID": requestId,
  };

  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(url, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    credentials: "include",
  });

  if (!res.ok) {
    if (res.status === 401 && typeof window !== "undefined") {
      window.location.href = "/login";
    }
    let code = "UNKNOWN";
    let message = `HTTP ${res.status}`;
    try {
      const envelope = (await res.json()) as {
        error?: { code?: string; message?: string };
      };
      if (envelope.error) {
        code = envelope.error.code ?? code;
        message = envelope.error.message ?? message;
      }
    } catch {
      // response body wasn't JSON
    }
    throw new ApiError(res.status, code, requestId, message);
  }

  return (await res.json()) as T;
}

export const apiClient = {
  get<T>(path: string, params?: Record<string, string>): Promise<T> {
    return request<T>("GET", path, undefined, params);
  },
  post<T>(path: string, body?: unknown): Promise<T> {
    return request<T>("POST", path, body);
  },
  put<T>(path: string, body?: unknown): Promise<T> {
    return request<T>("PUT", path, body);
  },
  delete<T>(path: string): Promise<T> {
    return request<T>("DELETE", path);
  },
};
