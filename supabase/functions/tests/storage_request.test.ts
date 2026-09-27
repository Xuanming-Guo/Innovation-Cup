import {
  MAX_AUDIO_BYTES,
  MAX_FILE_BYTES,
  MAX_IMAGE_BYTES,
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

const voice = {
  action: "create-upload",
  companyId: "11111111-1111-4111-8111-111111111111",
  demoRunId: "22222222-2222-4222-8222-222222222222",
  demoActorSessionId: "33333333-3333-4333-8333-333333333333",
  threadId: "44444444-4444-4444-8444-444444444444",
  contentType: "audio/webm",
  displayFilename: "recording.webm",
  purpose: "voice_audio",
  sizeBytes: MAX_AUDIO_BYTES,
};

Deno.test("voice binds a run, actor, thread and an eight MiB boundary", () => {
  const result = parseStorageTicketRequest(voice);
  assert(result.action === "create-upload", "expected voice upload");
  assert(result.demoRunId === voice.demoRunId, "run must be retained");
  assert(result.threadId === voice.threadId, "thread must be retained");
});

Deno.test("voice rejects missing thread, mixed purpose, excessive bytes and forged context", () => {
  const unsafe = [
    { ...voice, threadId: null },
    { ...voice, purpose: "evidence" },
    { ...voice, contentType: "image/png", displayFilename: "image.png" },
    { ...voice, taskId: voice.threadId },
    { ...voice, sourceId: voice.threadId },
    { ...voice, demoRunId: null },
    { ...voice, demoActorSessionId: "forged" },
    { ...voice, sizeBytes: MAX_AUDIO_BYTES + 1 },
  ];
  for (const candidate of unsafe) {
    let rejected = false;
    try {
      parseStorageTicketRequest(candidate);
    } catch (error) {
      rejected = error instanceof RequestValidationError;
    }
    assert(rejected, "unsafe voice upload must be rejected");
  }
});

Deno.test("work image enforces ten MiB without enabling SVG or extension spoofing", () => {
  const image = {
    action: "create-upload",
    companyId: voice.companyId,
    contentType: "image/png",
    displayFilename: "draft.png",
    purpose: "submission",
    taskId: voice.threadId,
    sizeBytes: MAX_IMAGE_BYTES,
  };
  assert(
    parseStorageTicketRequest(image).action === "create-upload",
    "bounded PNG allowed",
  );
  for (
    const candidate of [
      { ...image, sizeBytes: MAX_IMAGE_BYTES + 1 },
      { ...image, contentType: "image/svg+xml", displayFilename: "draft.svg" },
      { ...image, displayFilename: "draft.exe" },
    ]
  ) {
    let rejected = false;
    try {
      parseStorageTicketRequest(candidate);
    } catch (error) {
      rejected = error instanceof RequestValidationError;
    }
    assert(rejected, "unsafe image must be rejected");
  }
});
