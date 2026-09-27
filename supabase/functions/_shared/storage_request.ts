export const MAX_FILE_BYTES = 25 * 1024 * 1024;
export const MAX_IMAGE_BYTES = 10 * 1024 * 1024;
export const MAX_AUDIO_BYTES = 8 * 1024 * 1024;
export const ALLOWED_CONTENT_TYPES = new Set([
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "text/csv",
  "text/plain",
  "image/png",
  "image/jpeg",
  "audio/webm",
  "audio/mp4",
  "audio/wav",
]);

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export class RequestValidationError extends Error {}

export type CreateUploadRequest = {
  action: "create-upload";
  companyId: string;
  contentType: string;
  displayFilename: string;
  purpose: "source" | "submission" | "evidence" | "voice_audio";
  sizeBytes: number;
  sourceId: string | null;
  demoRunId: string | null;
  demoActorSessionId: string | null;
  taskId: string | null;
  threadId: string | null;
};

export type CreateDownloadRequest = {
  action: "create-download";
  companyId: string;
  fileId: string;
  demoRunId: string | null;
  demoActorSessionId: string | null;
};

export type StorageTicketRequest = CreateUploadRequest | CreateDownloadRequest;

function requiredString(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  if (typeof value !== "string" || value.length === 0) {
    throw new RequestValidationError(`${key} is required`);
  }
  return value;
}

function uuid(record: Record<string, unknown>, key: string): string {
  const value = requiredString(record, key);
  if (!UUID_PATTERN.test(value)) {
    throw new RequestValidationError(`${key} must be a UUID`);
  }
  return value.toLowerCase();
}

function hasControlCharacter(value: string): boolean {
  return [...value].some((character) => {
    const codePoint = character.codePointAt(0) ?? 0;
    return codePoint < 0x20 || codePoint === 0x7f;
  });
}

export function safeFileExtension(
  filename: string,
  contentType: string,
): string {
  const expected: Record<string, string> = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
      ".docx",
    "text/csv": ".csv",
    "text/plain": ".txt",
    "image/png": ".png",
    "image/jpeg": filename.toLowerCase().endsWith(".jpeg") ? ".jpeg" : ".jpg",
    "audio/webm": ".webm",
    "audio/mp4": ".mp4",
    "audio/wav": ".wav",
  };
  const extension = expected[contentType];
  if (!extension || !filename.toLowerCase().endsWith(extension)) {
    throw new RequestValidationError(
      "filename extension does not match contentType",
    );
  }
  return extension;
}

export function parseStorageTicketRequest(
  value: unknown,
): StorageTicketRequest {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new RequestValidationError("request body must be an object");
  }
  const record = value as Record<string, unknown>;
  const action = requiredString(record, "action");
  const companyId = uuid(record, "companyId");
  const demoRunId = record.demoRunId == null ? null : uuid(record, "demoRunId");
  const demoActorSessionId = record.demoActorSessionId == null
    ? null
    : uuid(record, "demoActorSessionId");
  if (demoActorSessionId !== null && demoRunId === null) {
    throw new RequestValidationError(
      "demoRunId is required for an actor session",
    );
  }

  if (action === "create-download") {
    return {
      action,
      companyId,
      fileId: uuid(record, "fileId"),
      demoRunId,
      demoActorSessionId,
    };
  }
  if (action !== "create-upload") {
    throw new RequestValidationError("action is not supported");
  }

  const displayFilename = requiredString(record, "displayFilename");
  if (displayFilename.length > 240 || hasControlCharacter(displayFilename)) {
    throw new RequestValidationError("displayFilename is invalid");
  }
  const contentType = requiredString(record, "contentType").toLowerCase();
  if (!ALLOWED_CONTENT_TYPES.has(contentType)) {
    throw new RequestValidationError("contentType is not supported");
  }
  safeFileExtension(displayFilename, contentType);

  const sizeBytes = record.sizeBytes;
  if (
    !Number.isSafeInteger(sizeBytes) || Number(sizeBytes) < 1 ||
    Number(sizeBytes) > MAX_FILE_BYTES
  ) {
    throw new RequestValidationError("sizeBytes is outside the allowed range");
  }
  const purpose = requiredString(record, "purpose");
  if (
    purpose !== "source" && purpose !== "submission" &&
    purpose !== "evidence" && purpose !== "voice_audio"
  ) {
    throw new RequestValidationError("purpose is not supported");
  }
  const sourceId = record.sourceId == null ? null : uuid(record, "sourceId");
  const taskId = record.taskId == null ? null : uuid(record, "taskId");
  const threadId = record.threadId == null ? null : uuid(record, "threadId");
  const isAudio = contentType.startsWith("audio/");
  if (
    isAudio !== (purpose === "voice_audio") ||
    (isAudio &&
      (threadId === null || sourceId !== null || taskId !== null ||
        Number(sizeBytes) > MAX_AUDIO_BYTES)) ||
    (contentType.startsWith("image/") && Number(sizeBytes) > MAX_IMAGE_BYTES)
  ) {
    throw new RequestValidationError(
      "purpose, context, or size is invalid for this content type",
    );
  }
  if (purpose === "source" && sourceId === null) {
    throw new RequestValidationError(
      "sourceId is required for a source upload",
    );
  }

  return {
    action,
    companyId,
    contentType,
    displayFilename,
    purpose,
    sizeBytes: Number(sizeBytes),
    sourceId,
    demoRunId,
    demoActorSessionId,
    taskId,
    threadId,
  };
}
