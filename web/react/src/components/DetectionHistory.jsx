import { useMemo, useState } from "react";
import Icon, { OBJECT_ICON } from "./Icon";
import { fmt, levelLabel, toneOf } from "../data";

const FILTERS = [
  { id: "all", label: "Semua" },
  { id: "danger", label: "Bahaya" },
  { id: "warn", label: "Waspada" },
  { id: "safe", label: "Info" },
];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];

// "2026-11-23 17:17:10" -> { date: "23 Nov 2026", clock: "17:17:10" }. Format lain dibiarkan apa adanya.
function splitWhen(value) {
  const text = String(value ?? "");
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}:\d{2}(?::\d{2})?)/);
  if (!match) return { date: "", clock: text || "-" };
  return { date: `${Number(match[3])} ${MONTHS[Number(match[2]) - 1] || match[2]} ${match[1]}`, clock: match[4] };
}

export default function DetectionHistory({ detections }) {
  const [filter, setFilter] = useState("all");

  const counts = useMemo(() => {
    const result = { all: detections.length, danger: 0, warn: 0, safe: 0 };
    detections.forEach((item) => { result[toneOf(item)] += 1; });
    return result;
  }, [detections]);

  const rows = filter === "all" ? detections : detections.filter((item) => toneOf(item) === filter);

  return (
    <section className="vc-panel" id="riwayat" aria-labelledby="riwayat-title">
      <div className="vc-panel-head">
        <div>
          <h2 className="vc-panel-title" id="riwayat-title">Riwayat deteksi</h2>
          <p className="vc-panel-sub">
            {detections.length ? `${detections.length} deteksi terakhir dari rompi` : "Objek yang terdeteksi rompi akan muncul di sini"}
          </p>
        </div>
        {detections.length > 0 && (
          <div className="vc-filters" role="group" aria-label="Filter tingkat risiko">
            {FILTERS.map((item) => (
              <button
                key={item.id}
                type="button"
                className="vc-filter"
                aria-pressed={filter === item.id}
                onClick={() => setFilter(item.id)}
              >
                {item.label} <i>{counts[item.id]}</i>
              </button>
            ))}
          </div>
        )}
      </div>

      {detections.length === 0 ? (
        <div className="vc-empty vc-tone-idle">
          <span className="vc-seg-chip"><Icon name="clock" size={20} /></span>
          <strong>Belum ada riwayat deteksi</strong>
          <span>Hasil deteksi akan muncul otomatis saat rompi mengirim data.</span>
        </div>
      ) : (
        <>
          <div className="vc-hist-head" aria-hidden="true">
            <span />
            <span>Objek</span>
            <span>Tanggal</span>
            <span>Waktu</span>
            <span>Jarak</span>
            <span>Arah</span>
            <span>Risiko</span>
          </div>
          {rows.length === 0 ? (
            <div className="vc-empty vc-tone-idle">
              <strong>Tidak ada deteksi pada kategori ini</strong>
              <span>Pilih kategori lain untuk melihat riwayat.</span>
            </div>
          ) : (
            <ul className="vc-history">
              {rows.map((d, i) => {
                const tone = toneOf(d);
                const when = splitWhen(d.time);
                return (
                  <li key={d.liveHistoryId || d.id || `${d.object}-${d.time}-${i}`} className={`vc-hist-item vc-tone-${tone}`}>
                    <span className="vc-hist-icon"><Icon name={OBJECT_ICON[d.object] || "alert"} size={20} /></span>
                    <div style={{ minWidth: 0 }}>
                      <p className="vc-hist-name">
                        {d.object}
                        {d.liveHistoryId && <span className="vc-badge vc-hist-live-badge">LIVE</span>}
                      </p>
                      <p className="vc-hist-meta">
                        <span>{[when.date, when.clock].filter(Boolean).join(" · ")}</span>
                        <span>{fmt(d.distance)} m</span>
                        {d.arah ? <span>{d.arah}</span> : null}
                      </p>
                    </div>
                    <span className="vc-hist-cell">{when.date || "-"}</span>
                    <span className="vc-hist-cell">{when.clock}</span>
                    <span className="vc-hist-cell"><b>{fmt(d.distance)} m</b></span>
                    <span className="vc-hist-cell" style={{ textTransform: "capitalize" }}>{d.arah || "-"}</span>
                    <span className="vc-badge vc-hist-badge">{levelLabel(d)}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
