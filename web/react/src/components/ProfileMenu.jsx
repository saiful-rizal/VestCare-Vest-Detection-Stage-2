import { useEffect, useRef, useState } from "react";
import avatar from "../assets/img/avatar.png";
import Icon from "./Icon";
import { COLOR, fmt, profile } from "../data";
import { supabase } from "../supabaseClient";

export default function ProfileMenu({ device, position, telemetry, telemetryOnline }) {
  const [open, setOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [logoutError, setLogoutError] = useState("");
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

  async function handleSignOut() {
    setSigningOut(true);
    setLogoutError("");
    try {
      const { error } = await supabase.auth.signOut();
      if (error) {
        setLogoutError(error.message);
        return;
      }
      setOpen(false);
    } catch (error) {
      setLogoutError(error instanceof Error ? error.message : String(error));
    } finally {
      setSigningOut(false);
    }
  }

  return (
    <div style={{ position: "relative" }} ref={ref}>
      <button
        type="button"
        className="vc-profile-btn"
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls="profileMenu"
        aria-label="Profil dan detail perangkat"
        onClick={() => {
          setOpen((o) => !o);
          setLogoutError("");
        }}
      >
        <img className="vc-avatar" src={avatar} alt="" />
        <Icon name="chevronDown" size={16} />
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
              <span className="vc-dot" style={{ display: "inline-block", marginRight: 6, background: online ? COLOR.Rendah : "#8a949e" }} />
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
          {logoutError && <p className="vc-menu-error" role="alert">{logoutError}</p>}
          <button className="vc-menu-logout" disabled={signingOut} onClick={handleSignOut} type="button">
            <svg aria-hidden="true" viewBox="0 0 24 24">
              <path d="M10 17l5-5-5-5m5 5H3m9-9h5a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-5" />
            </svg>
            {signingOut ? "Keluar..." : "Keluar"}
          </button>
        </div>
      )}
    </div>
  );
}
