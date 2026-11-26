import { fmt, toneOf } from "../data";

// Radar jarak: tampilan atas dengan rompi di bawah-tengah. Posisi objek diturunkan dari
// data yang sudah ada (arah kiri/depan/kanan dan jarak), tanpa memanggil API baru.
const CX = 130;
const CY = 148;
const PER_METER = 24; // 5 m = 120 unit
const MAX_METERS = 5;
const ANGLE = { kiri: -55, depan: 0, kanan: 55 };
const MAX_DOTS = 12;

const polar = (angleDeg, radius) => {
  const rad = (angleDeg * Math.PI) / 180;
  return { x: CX + radius * Math.sin(rad), y: CY - radius * Math.cos(rad) };
};
const arc = (radius) => `M ${CX - radius} ${CY} A ${radius} ${radius} 0 0 1 ${CX + radius} ${CY}`;

export default function ProximityRadar({ detections = [], distance = null, online = false }) {
  const dots = detections.slice(0, MAX_DOTS).map((item, index) => {
    const meters = Math.max(0.4, Math.min(Number(item.distance) || 1.5, MAX_METERS));
    const angle = (ANGLE[item.arah] ?? 0) + ((index % 3) - 1) * 9;
    return { item, tone: toneOf(item), ...polar(angle, meters * PER_METER), key: `${item.object}-${index}` };
  });

  const beamTone = distance == null ? "idle" : distance < 1 ? "danger" : distance < 2 ? "warn" : "safe";
  const beamEnd = distance == null ? null : polar(0, Math.min(distance, MAX_METERS) * PER_METER);
  const hasData = dots.length > 0 || distance != null;
  const wedgeA = polar(-9, 118);
  const wedgeB = polar(9, 118);

  return (
    <div className="vc-radar" role="img" aria-label={`Radar sekitar rompi. ${detections.length} objek terdeteksi.`}>
      <div className="vc-radar-head">
        <span>Radar sekitar</span>
        <span>{online ? "Memindai" : "Standby"}</span>
      </div>

      <svg viewBox="0 0 260 160" aria-hidden="true">
        <defs>
          <linearGradient id="vc-sweep-fill" x1="0" y1="1" x2="0" y2="0">
            <stop offset="0" stopColor="#ff4b55" stopOpacity="0.38" />
            <stop offset="1" stopColor="#ff4b55" stopOpacity="0" />
          </linearGradient>
        </defs>

        {[1, 2, 3, 4, 5].map((m) => (
          <path key={m} d={arc(m * PER_METER)} className={`vc-radar-ring${m === 5 ? " vc-radar-ring--edge" : ""}`} />
        ))}
        {[-55, 0, 55].map((a) => {
          const end = polar(a, 120);
          return <line key={a} x1={CX} y1={CY} x2={end.x} y2={end.y} className="vc-radar-guide" />;
        })}
        {[1, 3, 5].map((m) => (
          <text key={m} x={CX + 5} y={CY - m * PER_METER - 3} className="vc-radar-text">{m} m</text>
        ))}
        <text x={CX} y={14} textAnchor="middle" className="vc-radar-text">Depan</text>
        <text x={polar(-55, 130).x} y={polar(-55, 130).y + 2} textAnchor="end" className="vc-radar-text">Kiri</text>
        <text x={polar(55, 130).x} y={polar(55, 130).y + 2} textAnchor="start" className="vc-radar-text">Kanan</text>

        {online && (
          <g className="vc-radar-sweep">
            <path d={`M ${CX} ${CY} L ${wedgeA.x} ${wedgeA.y} A 118 118 0 0 1 ${wedgeB.x} ${wedgeB.y} Z`} fill="url(#vc-sweep-fill)" />
          </g>
        )}

        {beamEnd && (
          <g className={`vc-tone-${beamTone}`}>
            <line x1={CX} y1={CY - 10} x2={beamEnd.x} y2={beamEnd.y} className="vc-radar-beam" />
            <circle cx={beamEnd.x} cy={beamEnd.y} r="4.5" className="vc-radar-cap" />
          </g>
        )}

        {dots.map(({ item, tone, x, y, key }) => (
          <g key={key} className={`vc-tone-${tone}`}>
            {tone === "danger" && <circle cx={x} cy={y} r="6" className="vc-radar-halo" />}
            <circle cx={x} cy={y} r="6" className="vc-radar-dot">
              <title>{`${item.object} · ${fmt(item.distance)} m${item.arah ? ` · ${item.arah}` : ""}`}</title>
            </circle>
          </g>
        ))}

        <circle cx={CX} cy={CY} r="8" className="vc-radar-vest" />
        {!hasData && (
          <text x={CX} y={CY - 52} textAnchor="middle" className="vc-radar-text" style={{ fontSize: 10 }}>
            Menunggu data rompi
          </text>
        )}
      </svg>

      <p className="vc-radar-note">
        {distance != null ? <>Sensor depan <b>{fmt(distance)} m</b></> : "Sensor depan belum terbaca"}
        {" · "}
        <b>{detections.length}</b> objek
      </p>
    </div>
  );
}
