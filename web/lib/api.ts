/**
 * Typed API client for the Rustenwer backend (Phase 0).
 *
 * Contract mirror of `shared/README.md`. Domain types are imported from the
 * single source of truth (`shared/types.ts`) with `import type`, which is
 * erased at build time — no bundler path issues.
 *
 * Mock fallback: when the API is unreachable, the client throws
 * `ApiOfflineError`. Callers catch it and render the labeled mock dataset so
 * Phase 0 can be demoed before the backend is running.
 */
import type { Project, ProjectStatus } from "../../shared/types";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Phase 0 stub auth: any well-formed Bearer token is accepted by the API. */
const DEV_TOKEN = "phase0-dev-token";

export class ApiOfflineError extends Error {
  constructor(message = "API unreachable") {
    super(message);
    this.name = "ApiOfflineError";
  }
}

export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
  }
}

const REQUEST_TIMEOUT_MS = 8000;

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const res = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${DEV_TOKEN}`,
        ...(options.headers ?? {}),
      },
    });
    if (!res.ok) {
      let detail = `Request failed with status ${res.status}`;
      try {
        const body = (await res.json()) as { detail?: string };
        if (typeof body.detail === "string") detail = body.detail;
      } catch {
        // keep default detail
      }
      throw new ApiError(res.status, detail);
    }
    return (await res.json()) as T;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    throw new ApiOfflineError(
      `Could not reach ${API_BASE_URL}${path}: ${err instanceof Error ? err.message : String(err)}`,
    );
  } finally {
    clearTimeout(timeout);
  }
}

export function isApiOfflineError(err: unknown): err is ApiOfflineError {
  return err instanceof ApiOfflineError;
}

export async function checkHealth(): Promise<{
  status: string;
  service: string;
  version: string;
}> {
  return request("/health");
}

export async function listProjects(): Promise<Project[]> {
  return request<Project[]>("/api/v1/projects");
}

export async function getProject(id: string): Promise<Project> {
  return request<Project>(`/api/v1/projects/${encodeURIComponent(id)}`);
}

export async function createProject(input: {
  name: string;
  description?: string;
}): Promise<Project> {
  return request<Project>("/api/v1/projects", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function updateProject(
  id: string,
  input: Partial<Pick<Project, "name" | "description" | "status">>,
): Promise<Project> {
  return request<Project>(`/api/v1/projects/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

/** Soft-archives a project (DELETE → status ARCHIVED). */
export async function archiveProject(id: string): Promise<void> {
  await request<void>(`/api/v1/projects/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

// ---------------------------------------------------------------------------
// Mock fallback dataset (Phase 0 demo only).
// Served ONLY when the API is unreachable; the UI labels it as mock data.
// ---------------------------------------------------------------------------

const MOCK_ORG_ID = "00000000-0000-0000-0000-000000000001";

export const MOCK_PROJECTS: Project[] = [
  {
    id: "11111111-1111-1111-1111-111111111111",
    organization_id: MOCK_ORG_ID,
    name: "Support triage classifier",
    description:
      "Classify incoming support tickets into refund, bug, or how-to, and route each to the right queue.",
    status: "ACTIVE" satisfies ProjectStatus,
    created_by: null,
    created_at: "2026-09-20T14:32:00Z",
    updated_at: "2026-09-25T09:12:00Z",
  },
  {
    id: "22222222-2222-2222-2222-222222222222",
    organization_id: MOCK_ORG_ID,
    name: "Invoice anomaly detector",
    description:
      "Flag supplier invoices whose amounts deviate from historical patterns before they are paid.",
    status: "PAUSED" satisfies ProjectStatus,
    created_by: null,
    created_at: "2026-09-22T10:05:00Z",
    updated_at: "2026-09-24T17:48:00Z",
  },
  {
    id: "33333333-3333-3333-3333-333333333333",
    organization_id: MOCK_ORG_ID,
    name: "Lead scoring ranker",
    description:
      "Rank inbound leads by likelihood to convert so sales calls the hottest first.",
    status: "ACTIVE" satisfies ProjectStatus,
    created_by: null,
    created_at: "2026-09-25T08:20:00Z",
    updated_at: "2026-09-26T03:15:00Z",
  },
];
