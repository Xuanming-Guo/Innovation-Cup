import { pipeline } from "@supabase/middleware";
import { withSupabase } from "@supabase/server";
import { withPostgresClient } from "@supabase/server/middleware/postgres";

import {
  parseStorageTicketRequest,
  RequestValidationError,
  safeFileExtension,
} from "../_shared/storage_request.ts";

type TicketRow = {
  file_id: string;
  bucket_id: string;
  object_path: string;
  file_state: string;
};

function json(body: unknown, status = 200): Response {
  return Response.json(body, {
    status,
    headers: { "Cache-Control": "no-store" },
  });
}

const fetch = pipeline(
  [withSupabase({ auth: "user" }), withPostgresClient()],
  async (request, context) => {
    if (request.method !== "POST") {
      return json({ error: "method_not_allowed" }, 405);
    }

    try {
      const input = parseStorageTicketRequest(await request.json());
      const fileId = input.action === "create-upload"
        ? crypto.randomUUID()
        : input.fileId;
      const extension = input.action === "create-upload"
        ? safeFileExtension(input.displayFilename, input.contentType)
        : null;
      const objectPath = input.action === "create-upload"
        ? `${input.companyId}/${
          input.demoRunId ? `runs/${input.demoRunId}/` : ""
        }${fileId}/payload${extension}`
        : null;

      const rows = await context.postgres.query<TicketRow>`
        select file_id, bucket_id, object_path, file_state
        from app.issue_private_storage_ticket(
          ${input.action},
          ${input.companyId}::uuid,
          ${fileId}::uuid,
          ${objectPath},
          ${input.action === "create-upload" ? input.purpose : null},
          ${input.action === "create-upload" ? input.sourceId : null}::uuid,
          ${input.action === "create-upload" ? input.displayFilename : null},
          ${input.action === "create-upload" ? input.contentType : null},
          ${input.action === "create-upload" ? input.sizeBytes : null}::bigint,
          ${input.demoRunId}::uuid,
          ${input.demoActorSessionId}::uuid,
          ${input.action === "create-upload" ? input.taskId : null}::uuid,
          ${input.action === "create-upload" ? input.threadId : null}::uuid
        )
      `;
      const ticket = rows[0];
      if (!ticket) {
        return json({ error: "not_found" }, 404);
      }

      if (input.action === "create-upload") {
        const { data, error } = await context.supabaseAdmin.storage
          .from(ticket.bucket_id)
          .createSignedUploadUrl(ticket.object_path, { upsert: false });
        if (error || !data) {
          return json({ error: "storage_unavailable" }, 503);
        }
        return json({
          fileId: ticket.file_id,
          objectPath: ticket.object_path,
          signedUrl: data.signedUrl,
          token: data.token,
          uploadIntentExpiresInSeconds: 600,
          state: ticket.file_state,
        }, 201);
      }

      const configuredTtl = Number(
        Deno.env.get("STORAGE_DOWNLOAD_TTL_SECONDS") ?? "60",
      );
      const downloadTtlSeconds = Number.isInteger(configuredTtl)
        ? Math.min(Math.max(configuredTtl, 15), 300)
        : 60;
      const { data, error } = await context.supabaseAdmin.storage
        .from(ticket.bucket_id)
        .createSignedUrl(ticket.object_path, downloadTtlSeconds);
      if (error || !data) {
        return json({ error: "storage_unavailable" }, 503);
      }
      return json({
        fileId: ticket.file_id,
        signedUrl: data.signedUrl,
        expiresInSeconds: downloadTtlSeconds,
      });
    } catch (error) {
      if (
        error instanceof RequestValidationError || error instanceof SyntaxError
      ) {
        return json({ error: "invalid_request" }, 400);
      }
      return json({ error: "storage_ticket_failed" }, 500);
    }
  },
);

export default { fetch };
