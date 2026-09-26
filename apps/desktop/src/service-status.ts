import type { PublicRuntimeConfig } from "./runtime-config";

export type ServiceState = "checking" | "reachable" | "unreachable";

export interface ServiceStatus {
  apiVersion?: string;
  buildCommit?: string;
  detail: string;
  state: ServiceState;
}

interface VersionResponse {
  api_version: string;
  build_commit: string;
  service: string;
}

export async function getServiceStatus(
  config: PublicRuntimeConfig,
  signal?: AbortSignal,
): Promise<ServiceStatus> {
  try {
    const response = await fetch(`${config.apiOrigin}/version`, {
      headers: { Accept: "application/json" },
      signal,
    });

    if (!response.ok) {
      return {
        state: "unreachable",
        detail: `API returned HTTP ${response.status}`,
      };
    }

    const version = (await response.json()) as VersionResponse;
    return {
      state: "reachable",
      detail: "API foundation reachable",
      apiVersion: version.api_version,
      buildCommit: version.build_commit,
    };
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }

    return {
      state: "unreachable",
      detail: config.apiMode === "supabase-discovery"
        ? "The host computer is offline or still starting"
        : "Start the local API or configure VITE_API_ORIGIN",
    };
  }
}
