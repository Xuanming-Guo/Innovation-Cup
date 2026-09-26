interface HostDiscoveryClient {
  rpc(
    functionName: string,
    arguments_: Record<string, unknown>,
  ): PromiseLike<{ data: unknown; error: { message: string } | null }>;
}

export class HostOfflineError extends Error {
  constructor(message = "The host computer is offline or its endpoint lease has expired") {
    super(message);
    this.name = "HostOfflineError";
  }
}

export function normaliseDiscoveredApiOrigin(value: unknown): string {
  if (typeof value !== "string" || !value.trim()) throw new HostOfflineError();
  const url = new URL(value.trim());
  if (
    url.protocol !== "https:" ||
    url.username ||
    url.password ||
    url.pathname !== "/" ||
    url.search ||
    url.hash
  ) {
    throw new Error("Host discovery returned an invalid HTTPS origin");
  }
  return url.origin;
}

export async function resolveHostApiOrigin(
  client: HostDiscoveryClient,
  companyId: string,
): Promise<string> {
  const { data, error } = await client.rpc("resolve_coordination_host", {
    p_company_id: companyId,
  });
  if (error !== null) throw new Error("Host discovery is unavailable");
  return normaliseDiscoveredApiOrigin(data);
}
