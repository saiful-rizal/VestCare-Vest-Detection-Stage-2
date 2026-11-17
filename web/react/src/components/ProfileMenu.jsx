import { useEffect, useRef, useState } from "react";
import avatar from "../assets/img/avatar.png";
import { COLOR, fmt, profile } from "../data";

export default function ProfileMenu({ device, position, telemetry, telemetryOnline }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  // tutup saat klik di luar / tekan Escape
  useEffect(() => {
    const onClick = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const onKey = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("click", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("click", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  const online = telemetryOnline ?? device.online;
  const hasTelemetry = Boolean(telemetry?.updatedAt || telemetry?.fix || telemetry?.terbaca);
  const gpsLabel = telemetry?.fix
    ? "Fix"
    : telemetry?.terbaca
      ? "Mencari satelit"
      : hasTelemetry
        ? "Tidak terbaca"
        : "-";

  return (
    <li className="relative flex items-center" ref={ref}>
      <button
        type="button"
        className="vc-profile-btn"
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls="profileMenu"
        onClick={() => setOpen((o) => !o)}
      >
        <img className="vc-avatar" src={avatar} alt="Foto profil" />
        <span className="hidden sm:inline">Profil</span>
        <span className="vc-caret"></span>
      </button>

      {open && (
        <div id="profileMenu" className="vc-menu" role="dialog" aria-label="Profil pengguna">
          <div className="vc-menu-head">
            <img src={avatar} alt="" />
            <div><b>{device.studentName || profile.nama}</b><span>{device.school || profile.sekolah}</span></div>
          </div>
          <div className="vc-row"><span>Perangkat</span><span>{device.name || profile.perangkat}</span></div>
          <div className="vc-row">
            <span>Status rompi</span>
            <span>
              <span className="vc-dot" style={{ background: online ? COLOR.Rendah : "#9a8b88" }}></span>
              {online ? "Online" : "Offline"}
            </span>
          </div>
          <div className="vc-row">
            <span>Jarak sensor</span>
            <span>{telemetry?.jarak == null ? "-" : `${fmt(telemetry.jarak)} m`}</span>
          </div>
          <div className="vc-row">
            <span>GPS</span>
            <span>{gpsLabel}{telemetry?.fix ? ` · ${telemetry.sat} satelit` : ""}</span>
          </div>
          <div className="vc-row"><span>Lokasi terakhir</span><span>{position ? `${position.lat.toFixed(5)}, ${position.lng.toFixed(5)}` : "Belum tersedia"}</span></div>
        </div>
      )}
    </li>
  );
}
