export const READ_TIMEOUT_MS = 20_000;
export const COMMAND_TIMEOUT_MS = 120_000;

export class RequestTimeoutError extends Error {
  constructor(message = "The request timed out. Check the host connection and try again.") {
    super(message);
    this.name = "RequestTimeoutError";
  }
}

/** Bound the entire operation (including response parsing), even if a transport ignores abort. */
export async function withRequestDeadline<T>(
  operation: (signal: AbortSignal) => PromiseLike<T>,
  options: { signal?: AbortSignal | null; timeoutMs?: number; timeoutMessage?: string } = {},
): Promise<T> {
  const controller = new AbortController();
  const cancel = () => controller.abort(options.signal?.reason);
  if (options.signal?.aborted) cancel();
  else options.signal?.addEventListener("abort", cancel, { once: true });
  const timer = globalThis.setTimeout(
    () => controller.abort(new RequestTimeoutError(options.timeoutMessage)),
    options.timeoutMs ?? READ_TIMEOUT_MS,
  );
  let rejectAbort: () => void = () => undefined;
  const interrupted = new Promise<never>((_resolve, reject) => {
    rejectAbort = () => reject(controller.signal.reason ?? new DOMException("Request cancelled", "AbortError"));
    if (controller.signal.aborted) rejectAbort();
    else controller.signal.addEventListener("abort", rejectAbort, { once: true });
  });
  try {
    return await Promise.race([
      interrupted,
      Promise.resolve().then(() => {
        controller.signal.throwIfAborted();
        return operation(controller.signal);
      }),
    ]);
  } finally {
    globalThis.clearTimeout(timer);
    options.signal?.removeEventListener("abort", cancel);
    controller.signal.removeEventListener("abort", rejectAbort);
  }
}
