// A narrowly leased worker capability, not a public Storage proxy. No caller path
// or bucket is accepted. The database resolves both only after checking the lease.
import { createClient } from "npm:@supabase/supabase-js@2.117.2";

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const actions = new Set([
  "download-quarantine",
  "upload-private",
  "download-private",
  "delete-audio",
  "cleanup-expired-audio",
]);
const json = (value: unknown, status = 200) =>
  Response.json(value, {
    status,
    headers: { "Cache-Control": "no-store" },
  });

async function boundedBody(request: Request): Promise<unknown> {
  const reader = request.body?.getReader();
  if (!reader) throw new Error("empty body");
  const chunks: Uint8Array[] = [];
  let length = 0;
  try {
    while (true) {
      const part = await reader.read();
      if (part.done) break;
      length += part.value.byteLength;
      if (length > 2048) {
        await reader.cancel();
        throw new Error("oversized body");
      }
      chunks.push(part.value);
    }
  } finally {
    reader.releaseLock();
  }
  const bytes = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
}

export default {
  async fetch(request: Request): Promise<Response> {
    if (request.method !== "POST") {
      return json({ error: "method_not_allowed" }, 405);
    }
    let parsed: unknown;
    try {
      parsed = await boundedBody(request);
    } catch {
      return json({ error: "invalid_request" }, 400);
    }
    try {
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        return json({ error: "invalid_request" }, 400);
      }
      const body = parsed as Record<string, unknown>;
      const cleanup = body?.action === "cleanup-expired-audio";
      const allowed = cleanup
        ? ["fileId", "cleanupToken", "action"]
        : ["companyId", "jobId", "leaseToken", "fileId", "action"];
      if (
        !body || typeof body !== "object" || Array.isArray(body) ||
        Object.keys(body).some((key) => !allowed.includes(key)) ||
        !(cleanup
          ? [body.fileId, body.cleanupToken]
          : [body.companyId, body.jobId, body.leaseToken, body.fileId]).every((
            value,
          ) => typeof value === "string" && uuid.test(value)) ||
        typeof body.action !== "string" || !actions.has(body.action)
      ) return json({ error: "invalid_request" }, 400);
      const url = Deno.env.get("SUPABASE_URL");
      const key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
      if (!url || !key) return json({ error: "storage_unavailable" }, 503);
      const client = createClient(url, key, {
        auth: { persistSession: false, autoRefreshToken: false },
      });
      const { data: ticket, error } = cleanup
        ? await client.rpc("authorize_alto_audio_cleanup", {
          p_file_id: body.fileId,
          p_cleanup_token: body.cleanupToken,
        })
        : await client.rpc("authorize_alto_worker_storage", {
          p_company_id: body.companyId,
          p_job_id: body.jobId,
          p_lease_token: body.leaseToken,
          p_file_id: body.fileId,
          p_action: body.action,
        });
      if (error || !ticket) return json({ error: "not_found" }, 404);
      if (body.action === "delete-audio" || cleanup) {
        for (const object of ticket.object_paths) {
          const result = await client.storage.from(object.bucket_id).remove([
            object.object_path,
          ]);
          if (result.error) return json({ error: "storage_unavailable" }, 503);
        }
        if (cleanup) {
          const result = await client.rpc("complete_alto_audio_cleanup", {
            p_file_id: body.fileId,
            p_cleanup_token: body.cleanupToken,
          });
          if (result.error || !result.data) {
            return json({ error: "cleanup_completion_conflict" }, 409);
          }
        }
        return json({ deleted: true });
      }
      const storage = client.storage.from(ticket.bucket_id);
      const result = body.action === "upload-private"
        ? await storage.createSignedUploadUrl(ticket.object_path, {
          upsert: false,
        })
        : await storage.createSignedUrl(ticket.object_path, 60);
      if (result.error || !result.data) {
        return json({ error: "storage_unavailable" }, 503);
      }
      return json({
        signed_url: result.data.signedUrl,
        bucket_id: ticket.bucket_id,
        object_path: ticket.object_path,
        content_type: ticket.content_type,
        size_bytes: ticket.size_bytes,
        // Supabase upload tokens have provider-defined two-hour validity; DB
        // clean-state publication remains separately fenced to the active lease.
        expires_in_seconds: body.action === "upload-private" ? 7200 : 60,
      });
    } catch {
      // Never log a lease token, signed URL, storage key, or provider exception.
      return json({ error: "storage_capability_failed" }, 500);
    }
  },
};
