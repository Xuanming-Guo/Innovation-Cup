import { altoRequest, type AltoApiContext } from "./alto-api";
import { loadPublicRuntimeConfig } from "./runtime-config";
interface UploadTicket {
    fileId: string;
    signedUrl: string;
    state: string;
}
async function ticket<T>(api: AltoApiContext, body: Record<string, unknown>): Promise<T> {
    const config = loadPublicRuntimeConfig();
    if (!config.supabaseUrl || !config.supabasePublishableKey)
        throw new Error("Private storage is not configured.");
    const response = await fetch(`${config.supabaseUrl}/functions/v1/storage-ticket`, {
        method: "POST", headers: { Authorization: `Bearer ${api.accessToken}`, apikey: config.supabasePublishableKey, "Content-Type": "application/json" },
        body: JSON.stringify({ ...body, companyId: api.companyId, ...(api.demoRunId ? { demoRunId: api.demoRunId } : {}), ...(api.demoActorSessionId ? { demoActorSessionId: api.demoActorSessionId } : {}) }),
    });
    if (!response.ok)
        throw new Error(`Private file access was not authorised or storage is unavailable (${response.status}).`);
    return response.json() as Promise<T>;
}
function assertStorageUrl(signedUrl: string) {
    const config = loadPublicRuntimeConfig();
    const url = new URL(signedUrl);
    if (url.origin !== config.supabaseUrl || !url.pathname.startsWith("/storage/v1/"))
        throw new Error("The storage ticket returned an unexpected destination.");
}
export async function uploadPrivateFile(api: AltoApiContext, file: Blob, filename: string, purpose: "submission" | "voice_audio", binding: {
    taskId?: string;
    threadId?: string;
} = {}): Promise<{
    file_id: string;
    state: string;
}> {
    const maxSize = purpose === "voice_audio" ? 8 * 1024 * 1024 : 25 * 1024 * 1024;
    if (!file.size || file.size > maxSize)
        throw new Error(`File must be nonempty and smaller than ${maxSize / 1024 / 1024} MiB.`);
    const contentType = file.type.split(";")[0] ?? "";
    if (!contentType) throw new Error("This file has no recognised content type. Choose a supported file format.");
    const authorised = await ticket<UploadTicket>(api, { action: "create-upload", purpose, displayFilename: filename, contentType, sizeBytes: file.size, sourceId: null, ...binding });
    assertStorageUrl(authorised.signedUrl);
    const uploaded = await fetch(authorised.signedUrl, { method: "PUT", headers: { "Content-Type": contentType, "x-upsert": "false" }, body: file });
    if (!uploaded.ok)
        throw new Error(`Private upload failed (${uploaded.status}). The file has not been submitted.`);
    const finalized = await altoRequest<{
        state: string;
    }>(api, `/files/${authorised.fileId}/finalize`, { method: "POST", body: { size_bytes: file.size } });
    return { file_id: authorised.fileId, state: finalized.state };
}
export async function downloadPrivateFile(api: AltoApiContext, fileId: string): Promise<void> {
    const authorised = await ticket<{
        signedUrl: string;
    }>(api, { action: "create-download", fileId });
    assertStorageUrl(authorised.signedUrl);
    const response = await fetch(authorised.signedUrl);
    if (!response.ok)
        throw new Error("This file is no longer available for download.");
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = "alto-private-file";
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 10000);
}
