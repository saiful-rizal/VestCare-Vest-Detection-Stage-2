import { useEffect, useRef, useState } from "react";
import { normalizeDetections } from "../data";

const API_URL = "/deteksi";

function createSilentWavUrl() {
  const sampleRate = 8000;
  const sampleCount = 800;
  const dataSize = sampleCount * 2;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);
  const writeText = (offset, text) => {
    for (let index = 0; index < text.length; index += 1) {
      view.setUint8(offset + index, text.charCodeAt(index));
    }
  };

  writeText(0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeText(8, "WAVE");
  writeText(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeText(36, "data");
  view.setUint32(40, dataSize, true);

  return URL.createObjectURL(new Blob([buffer], { type: "audio/wav" }));
}

export default function CameraCapture({ onDetections }) {
  const inputRef = useRef(null);
  const videoRef = useRef(null);
  const boxesRef = useRef(null);
  const audioRef = useRef(null);
  const silentAudioUrlRef = useRef(null);
  const audioUnlockedRef = useRef(false);
  const audioTokenRef = useRef(0);
  const cancelPlaybackRef = useRef(null);
  const streamRef = useRef(null);
  const detectingRef = useRef(false);
  const onDetectionsRef = useRef(onDetections);
  const [preview, setPreview] = useState(null);
  const [file, setFile] = useState(null);
  const [liveDetections, setLiveDetections] = useState([]);
  const [status, setStatus] = useState("idle");
  const [message, setMessage] = useState("");

  useEffect(() => {
    onDetectionsRef.current = onDetections;
  }, [onDetections]);

  useEffect(() => () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    audioTokenRef.current += 1;
    cancelPlaybackRef.current?.();
    audioRef.current?.pause();
    if (silentAudioUrlRef.current) URL.revokeObjectURL(silentAudioUrlRef.current);
  }, []);

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview);
  }, [preview]);

  useEffect(() => {
    const audio = new Audio();
    audio.preload = "auto";
    audioRef.current = audio;
    silentAudioUrlRef.current = createSilentWavUrl();

    return () => {
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
      audioRef.current = null;
    };
  }, []);

  function stopAudio() {
    audioTokenRef.current += 1;
    cancelPlaybackRef.current?.();
    cancelPlaybackRef.current = null;
    const audio = audioRef.current;
    if (!audio) return;
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
  }

  async function unlockAudio() {
    const audio = audioRef.current;
    const silentUrl = silentAudioUrlRef.current;
    if (!audio || !silentUrl || audioUnlockedRef.current) return audioUnlockedRef.current;

    try {
      audio.src = silentUrl;
      await audio.play();
      audio.pause();
      audio.currentTime = 0;
      audio.removeAttribute("src");
      audio.load();
      audioUnlockedRef.current = true;
      return true;
    } catch {
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
      setMessage("Suara belum diizinkan browser. Aktifkan suara lalu buka kamera kembali.");
      return false;
    }
  }

  function playUrl(url) {
    const audio = audioRef.current;
    if (!audio) return Promise.reject(new Error("Pemutar suara tidak tersedia."));

    return new Promise((resolve, reject) => {
      let settled = false;
      const cleanup = () => {
        audio.removeEventListener("ended", onEnded);
        audio.removeEventListener("error", onError);
        if (cancelPlaybackRef.current === cancel) cancelPlaybackRef.current = null;
      };
      const finish = (callback, value) => {
        if (settled) return;
        settled = true;
        cleanup();
        callback(value);
      };
      const onEnded = () => finish(resolve);
      const onError = () => finish(reject, new Error("Berkas suara tidak dapat diputar."));
      const cancel = () => finish(reject, new Error("Pemutaran suara dihentikan."));

      cancelPlaybackRef.current = cancel;
      audio.addEventListener("ended", onEnded);
      audio.addEventListener("error", onError);
      audio.src = url;
      audio.play().catch((error) => finish(reject, error));
    });
  }

  async function playPlan(plan) {
    if (!plan || !Array.isArray(plan.segmen) || !plan.segmen.length) {
      setMessage("Instruksi suara tidak tersedia untuk hasil deteksi ini.");
      return;
    }
    if (!audioUnlockedRef.current) {
      setMessage("Hasil terdeteksi, tetapi suara belum diizinkan browser. Tutup lalu buka kamera kembali.");
      return;
    }

    stopAudio();
    const token = audioTokenRef.current;
    setMessage(`Memutar instruksi ${plan.level}...`);
    try {
      for (const segment of plan.segmen) {
        if (token !== audioTokenRef.current) return;
        await playUrl(segment.url);
      }
      if (token === audioTokenRef.current) {
        setMessage(`Instruksi ${plan.level} selesai diputar.`);
      }
    } catch (error) {
      if (token === audioTokenRef.current) {
        setMessage(`Suara gagal diputar: ${error.message}`);
      }
    }
  }

  useEffect(() => {
    if (status !== "camera") return undefined;

    const video = videoRef.current;
    const stream = streamRef.current;
    if (!video || !stream) return undefined;

    video.srcObject = stream;
    video.play().catch(() => {});

    return () => {
      video.srcObject = null;
    };
  }, [status]);

  useEffect(() => {
    if (status !== "camera") return undefined;

    let active = true;
    let timer;
    let alertKey = null;
    let alertLevel = 0;
    let lastAlertAt = 0;
    let lastSpokenAt = 0;

    function renderBoxes(detections) {
      const video = videoRef.current;
      const canvas = boxesRef.current;
      if (!video || !canvas) return;

      const { width, height } = video.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      const context = canvas.getContext("2d");
      if (!context) return;

      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, width, height);
      if (!video.videoWidth || !video.videoHeight) return;

      const scale = Math.min(width / video.videoWidth, height / video.videoHeight);
      const offsetX = (width - video.videoWidth * scale) / 2;
      const offsetY = (height - video.videoHeight * scale) / 2;
      context.font = "600 13px system-ui, sans-serif";
      context.lineWidth = 3;

      detections.forEach((detection, index) => {
        const [left, top, right, bottom] = detection.bbox || [];
        if (![left, top, right, bottom].every(Number.isFinite)) return;

        const x = offsetX + left * video.videoWidth * scale;
        const y = offsetY + top * video.videoHeight * scale;
        const boxWidth = (right - left) * video.videoWidth * scale;
        const boxHeight = (bottom - top) * video.videoHeight * scale;
        const color = detection.level === "BAHAYA" ? "#ff4055"
          : detection.level === "WASPADA" ? "#ffbd35"
          : detection.level === "INFO" ? "#46dd91" : "#31c7e8";
        const label = `${index + 1}. ${detection.object} | ${detection.level} | ${detection.distance.toFixed(1)} m`;

        context.strokeStyle = color;
        context.strokeRect(x, y, boxWidth, boxHeight);
        context.fillStyle = color;
        const labelY = Math.max(0, y - 24);
        context.fillRect(x, labelY, context.measureText(label).width + 12, 22);
        context.fillStyle = "#102a43";
        context.fillText(label, x + 6, labelY + 15);
      });
    }

    async function detectFrame() {
      const video = videoRef.current;
      if (!active) return;
      if (!video || !video.videoWidth || detectingRef.current) {
        timer = window.setTimeout(detectFrame, 250);
        return;
      }

      detectingRef.current = true;
      const canvas = document.createElement("canvas");
      const scale = Math.min(1, 640 / video.videoWidth);
      canvas.width = Math.round(video.videoWidth * scale);
      canvas.height = Math.round(video.videoHeight * scale);
      const context = canvas.getContext("2d");

      try {
        if (!context) throw new Error("Tidak dapat menyiapkan gambar kamera.");
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        const blob = await new Promise((resolve, reject) => {
          canvas.toBlob((value) => value
            ? resolve(value)
            : reject(new Error("Gagal mengambil gambar kamera.")), "image/jpeg", 0.8);
        });
        if (!active) return;

        const body = new FormData();
        body.append("gambar", blob, "vest-care-live.jpg");
        const response = await fetch(API_URL, { method: "POST", body });
        const payload = await response.json().catch(() => ({}));
        if (!active) return;
        if (!response.ok) throw new Error(payload.detail || `Server deteksi mengembalikan ${response.status}.`);

        const detections = normalizeDetections(payload);
        setLiveDetections(detections);
        renderBoxes(detections);
        let saveError = null;
        try {
          await onDetectionsRef.current(detections);
        } catch (error) {
          saveError = error instanceof Error ? error.message : "Gagal mengirim deteksi ke Supabase.";
        }
        const alerts = detections.filter((detection) => detection.level !== "AMAN");
        const now = Date.now();

        if (alerts.length) {
          lastAlertAt = now;
          const top = alerts[0];
          const nextKey = `${top.object}:${top.arah}`;
          const nextLevel = { AMAN: 0, INFO: 1, WASPADA: 2, BAHAYA: 3 }[top.level] || 0;
          if ((nextKey !== alertKey || nextLevel > alertLevel) && now - lastSpokenAt >= 1800) {
            alertKey = nextKey;
            alertLevel = nextLevel;
            lastSpokenAt = now;
            void playPlan(payload.suara);
          } else if (audioRef.current?.paused) {
            setMessage(`${alerts.length} rintangan terdeteksi. Peringatan ${top.level}.`);
          }
        } else if (detections.length) {
          lastAlertAt = now;
          const top = detections[0];
          const nextKey = `${top.object}:${top.arah}`;
          if ((nextKey !== alertKey || alertLevel > 0) && now - lastSpokenAt >= 1800) {
            alertKey = nextKey;
            alertLevel = 0;
            lastSpokenAt = now;
            void playPlan(payload.suara);
          } else if (audioRef.current?.paused) {
            setMessage(`${detections.length} objek terdeteksi: ${top.object} ${top.arah}.`);
          }
        } else {
          if (now - lastAlertAt > 3500) {
            alertKey = null;
            alertLevel = 0;
          }
          if (audioRef.current?.paused) {
            setMessage("Kamera aktif. Tidak ada objek yang cukup yakin.");
          }
        }
        if (saveError) setMessage(`Deteksi berhasil, tetapi gagal disimpan ke Supabase: ${saveError}`);
      } catch (error) {
        if (active) {
          setMessage(error instanceof Error ? `Deteksi gagal: ${error.message}` : "Deteksi real-time gagal.");
        }
      } finally {
        detectingRef.current = false;
        if (active) timer = window.setTimeout(detectFrame, 1000);
      }
    }

    setMessage("Kamera aktif. Deteksi otomatis sedang berjalan.");
    void detectFrame();
    return () => {
      active = false;
      window.clearTimeout(timer);
      detectingRef.current = false;
    };
  }, [status]);

  async function openCamera() {
    if (!navigator.mediaDevices?.getUserMedia) {
      inputRef.current?.click();
      return;
    }

    try {
      const audioReady = unlockAudio();
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" } },
        audio: false,
      });
      await audioReady;
      streamRef.current = stream;
      setStatus("camera");
      setMessage("");
      setLiveDetections([]);
      setPreview(null);
      setFile(null);
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? `Kamera tidak dapat dibuka: ${error.message}` : "Kamera tidak dapat dibuka.");
    }
  }

  function handleFileChange(event) {
    const selectedFile = event.target.files?.[0];
    if (!selectedFile) return;

    if (preview) URL.revokeObjectURL(preview);
    setFile(selectedFile);
    setPreview(URL.createObjectURL(selectedFile));
    setStatus("ready");
    setMessage("");
  }

  function closePreview() {
    stopAudio();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setLiveDetections([]);
    onDetectionsRef.current([]);
    if (preview) URL.revokeObjectURL(preview);
    setPreview(null);
    setFile(null);
    setStatus("idle");
    setMessage("");
    if (inputRef.current) inputRef.current.value = "";
  }

  async function submitDetection() {
    if (!file) return;

    await unlockAudio();
    setStatus("loading");
    setMessage("");
    const body = new FormData();
    body.append("gambar", file);

    try {
      const response = await fetch(API_URL, {
        method: "POST",
        body,
      });

      if (!response.ok) {
        throw new Error(`Server deteksi mengembalikan ${response.status}.`);
      }

      const payload = await response.json();
      const detections = normalizeDetections(payload);
      let saveError = null;
      try {
        await onDetections(detections);
      } catch (error) {
        saveError = error instanceof Error ? error.message : "Gagal mengirim deteksi ke Supabase.";
      }
      setLiveDetections(detections);
      setStatus("success");
      setMessage(detections.length
        ? `${detections.length} objek terdeteksi.`
        : "Tidak ada objek yang cukup yakin.");
      if (payload.suara) await playPlan(payload.suara);
      if (saveError) setMessage(`Deteksi berhasil, tetapi gagal disimpan ke Supabase: ${saveError}`);
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "Deteksi gagal diproses.");
    }
  }

  return (
    <>
      <button
        type="button"
        className="vc-camera-fab"
        aria-label="Ambil foto untuk deteksi"
        onClick={openCamera}
      >
        <i className="ni ni-camera-compact" aria-hidden="true"></i>
        <span>Deteksi</span>
      </button>
      <input
        ref={inputRef}
        className="hidden"
        type="file"
        accept="image/*"
        capture="environment"
        onChange={handleFileChange}
      />

      {preview && (
        <div className="vc-camera-backdrop" role="dialog" aria-modal="true" aria-label="Pratinjau foto">
          <div className="vc-camera-dialog">
            <div className="flex items-center justify-between mb-4">
              <h2 className="mb-0 text-lg font-bold text-slate-800">Deteksi dari kamera</h2>
              <button type="button" className="vc-camera-close" onClick={closePreview} aria-label="Tutup">×</button>
            </div>
            <img className="vc-camera-preview" src={preview} alt="Pratinjau foto yang dipilih" />
            {message && <p className={`vc-camera-message ${status === "error" ? "is-error" : ""}`}>{message}</p>}
            <div className="flex justify-end gap-2 mt-4">
              <button type="button" className="vc-camera-secondary" onClick={openCamera}>Ambil ulang</button>
              <button type="button" className="vc-camera-primary" onClick={submitDetection} disabled={status === "loading"}>
                {status === "loading" ? "Memproses..." : "Kirim untuk deteksi"}
              </button>
            </div>
          </div>
        </div>
      )}
      {status === "camera" && (
        <div className="vc-camera-backdrop" role="dialog" aria-modal="true" aria-label="Kamera">
          <div className="vc-camera-dialog">
            <div className="flex items-center justify-between mb-4">
              <h2 className="mb-0 text-lg font-bold text-slate-800">Ambil foto deteksi</h2>
              <button type="button" className="vc-camera-close" onClick={closePreview} aria-label="Tutup">×</button>
            </div>
            <div className="vc-camera-stage">
              <video ref={videoRef} className="vc-camera-preview" autoPlay playsInline muted />
              <canvas ref={boxesRef} className="vc-camera-boxes" aria-hidden="true" />
              <span className="vc-camera-count" role="status">
                {liveDetections.length} objek terdeteksi
              </span>
            </div>
            {message && <p className={`vc-camera-message ${message.startsWith("Deteksi gagal:") ? "is-error" : ""}`} role="status">{message}</p>}
            {liveDetections.length > 0 && (
              <ul className="vc-camera-results">
                {liveDetections.map((detection, index) => (
                  <li key={`${detection.object}-${detection.arah}-${index}`}>
                    <strong>{detection.level} | {detection.object} {detection.arah}</strong>
                    <span>{detection.distance.toFixed(1)} m | confidence {Math.round(detection.confidence)}%</span>
                  </li>
                ))}
              </ul>
            )}
            <div className="flex justify-end gap-2 mt-4">
              <button type="button" className="vc-camera-secondary" onClick={closePreview}>Batal</button>
              <span className="vc-camera-live-status">● Deteksi otomatis aktif</span>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
