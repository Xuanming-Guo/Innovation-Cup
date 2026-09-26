import {
  MAX_FILE_BYTES,
  parseStorageTicketRequest,
  RequestValidationError,
} from "../_shared/storage_request.ts";

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

Deno.test("parses a bounded source upload without accepting a client path", () => {
  const result = parseStorageTicketRequest({
    action: "create-upload",
    companyId: "11111111-1111-4111-8111-111111111111",
    contentType: "text/plain",
    displayFilename: "brief.txt",
    purpose: "source",
    sizeBytes: 128,
    sourceId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    objectPath: "attacker-controlled",
  });
  assert(result.action === "create-upload", "expected upload request");
  assert(!("objectPath" in result), "client path must not survive parsing");
});

Deno.test("rejects unsupported or oversized uploads", () => {
  for (
    const candidate of [
      {
        action: "create-upload",
        companyId: "11111111-1111-4111-8111-111111111111",
        contentType: "text/html",
        displayFilename: "payload.html",
        purpose: "evidence",
        sizeBytes: 128,
      },
      {
        action: "create-upload",
        companyId: "11111111-1111-4111-8111-111111111111",
        contentType: "application/pdf",
        displayFilename: "payload.pdf",
        purpose: "evidence",
        sizeBytes: MAX_FILE_BYTES + 1,
      },
    ]
  ) {
    let rejected = false;
    try {
      parseStorageTicketRequest(candidate);
    } catch (error) {
      rejected = error instanceof RequestValidationError;
    }
    assert(rejected, "unsafe upload should be rejected");
  }
});

Deno.test("parses a download using only company and opaque file identity", () => {
  const result = parseStorageTicketRequest({
    action: "create-download",
    companyId: "11111111-1111-4111-8111-111111111111",
    fileId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    objectPath: "ignored",
  });
  assert(result.action === "create-download", "expected download request");
  assert(!("objectPath" in result), "download path must remain server-side");
});
