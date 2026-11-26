// Helper komunikasi API VestCare.
//
// Semua request dashboard memakai cookie sesi HttpOnly yang dipasang server.
// Jika cookie kedaluwarsa (12 jam), request 401 dicoba ulang sekali setelah
// meminta sesi baru ke /sesi. Dengan begitu kamera dan polling tetap berjalan
// tanpa pengguna harus memuat ulang halaman.

let sessionPromise = null;
const DEFAULT_REQUEST_TIMEOUT_MS = 20000;

export function errorMessage(payload, fallback) {
  const detail = payload?.detail ?? payload?.error ?? payload?.message;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const pesan = detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (!item || typeof item !== "object") return String(item);
        const lokasi = Array.isArray(item.loc) ? item.loc.filter(Boolean).join(".") : "";
        return `${lokasi ? `${lokasi}: ` : ""}${item.msg || JSON.stringify(item)}`;
      })
      .filter(Boolean)
      .join("; ");
    if (pesan) return pesan;
  }
  if (detail && typeof detail === "object") {
    if (typeof detail.pesan === "string") return detail.pesan;
    try {
      return JSON.stringify(detail);
    } catch {
      return fallback;
    }
  }
  return fallback;
}

async function refreshSession() {
  if (!sessionPromise) {
    sessionPromise = fetchWithTimeout("/sesi", {
      credentials: "same-origin",
      cache: "no-store",
      headers: { "ngrok-skip-browser-warning": "1" },
    }, 10000)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Sesi server gagal diperbarui (${response.status}).`);
        }
        return response.json().catch(() => ({}));
      })
      .finally(() => {
        sessionPromise = null;
      });
  }
  return sessionPromise;
}

async function fetchWithTimeout(input, init, timeoutMs) {
  const controller = new AbortController();
  const callerSignal = init.signal;
  const abortFromCaller = () => controller.abort();
  if (callerSignal?.aborted) {
    controller.abort();
  } else {
    callerSignal?.addEventListener("abort", abortFromCaller, { once: true });
  }
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(input, {
      ...init,
      signal: controller.signal,
    });
  } catch (error) {
    if (!callerSignal?.aborted && controller.signal.aborted) {
      const path = typeof input === "string" ? input : input.url;
      throw new Error(`Request ${path} timeout setelah ${timeoutMs / 1000} detik.`);
    }
    throw error;
  } finally {
    clearTimeout(timeout);
    callerSignal?.removeEventListener("abort", abortFromCaller);
  }
}

export async function apiFetch(
  input,
  init = {},
  { retry = true, timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS } = {},
) {
  const response = await fetchWithTimeout(input, {
    credentials: "same-origin",
    cache: "no-store",
    ...init,
    headers: {
      "ngrok-skip-browser-warning": "1",
      ...(init.headers || {}),
    },
  }, timeoutMs);

  if (response.status === 401 && retry) {
    try {
      await refreshSession();
    } catch {
      return response;
    }
    return apiFetch(input, init, { retry: false, timeoutMs });
  }
  return response;
}

export async function getJson(url, init = {}) {
  const response = await apiFetch(url, init);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(errorMessage(
      payload,
      `Server VestCare mengembalikan ${response.status}.`,
    ));
  }
  return payload;
}
