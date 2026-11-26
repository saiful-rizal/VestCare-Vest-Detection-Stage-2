import StatCard from "./StatCard";
import ProximityRadar from "./ProximityRadar";
import Icon, { OBJECT_ICON } from "./Icon";
import { fmt, levelLabel, profile, toneOf } from "../data";

const METER_SEGMENTS = 8;
const METER_MAX_M = 4;

export default function StatCards({ device, detections, telemetry, telemetryOnline, historyLoading, historyError }) {
  const online = telemetryOnline ?? device.online;
  const distance = telemetry?.jarak ?? null;
  const distanceTone = distance == null ? "idle" : distance < 1 ? "danger" : distance < 2 ? "warn" : "safe";
  const distanceLabel = distance == null
    ? telemetry?.terbaca ? "Di luar jangkauan" : "Menunggu rompi"
    : distance < 1 ? "Sangat dekat" : distance < 2 ? "Dekat" : "Aman";

  // makin dekat objek, makin banyak segmen yang menyala
  const lit = distance == null
    ? 0
    : Math.max(1, Math.round((1 - Math.min(distance, METER_MAX_M) / METER_MAX_M) * METER_SEGMENTS));

  const d = detections[0];
  const dTone = d ? toneOf(d) : "idle";
  const emptyNote = historyError || (historyLoading ? "Memuat riwayat server" : "Belum ada deteksi");

  const headline = online
    ? dTone === "danger" ? "Ada objek berbahaya di dekat siswa" : "Rompi aktif dan terpantau"
    : "Menunggu rompi terhubung";

  return (
    <section className="vc-hero" id="ringkasan" aria-label="Ringkasan status">
      <div className="vc-hero-main">
        <div>
          <p className="vc-eyebrow">
            <span className={`vc-dot vc-tone-${online ? "safe" : "idle"}`} />
            Ringkasan realtime
          </p>
          <h2 className="vc-hero-title">{headline}</h2>
          <p className="vc-hero-sub">
            {device.studentName || profile.nama} · {device.school || profile.sekolah}
          </p>
        </div>

        <div className="vc-kpis">
          <StatCard
            label="Status rompi"
            icon={<Icon name="wifi" size={15} />}
            value={online ? "Online" : "Offline"}
            tone={online ? "safe" : "idle"}
            note={online ? "Aktif mengirim data" : "Tidak ada data masuk"}
          />

          <StatCard
            label="Jarak depan"
            icon={<Icon name="ruler" size={15} />}
            value={distance == null ? "-" : <span className="vc-num">{fmt(distance)} m</span>}
            tone={distanceTone}
            note={<b>{distanceLabel}</b>}
          >
            <div className="vc-meter" aria-hidden="true">
              {Array.from({ length: METER_SEGMENTS }, (_, i) => <i key={i} data-on={i < lit} />)}
            </div>
          </StatCard>

          <StatCard
            label="Deteksi terakhir"
            icon={<Icon name="camera" size={15} />}
            value={
              <>
                {d && <span className="vc-seg-chip"><Icon name={OBJECT_ICON[d.object] || "alert"} size={17} /></span>}
                {d?.object || "-"}
              </>
            }
            tone={dTone}
            note={d ? <><b>{fmt(d.distance)} m</b> dari rompi</> : emptyNote}
          />

          <StatCard
            label="Tingkat risiko"
            icon={<Icon name="alert" size={15} />}
            value={d ? <span className="vc-badge vc-badge--lg">{levelLabel(d)}</span> : "-"}
            tone={dTone}
            note={d ? <>Keyakinan model <b>{Math.round(d.confidence)}%</b></> : emptyNote}
          />
        </div>
      </div>

      <ProximityRadar detections={detections} distance={distance} online={Boolean(online)} />
    </section>
  );
}
