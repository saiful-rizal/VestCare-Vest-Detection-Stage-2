import { useEffect, useState } from "react";
import ProfileMenu from "./ProfileMenu";
import Icon from "./Icon";
import logo from "../assets/img/favicon.png";
import { profile } from "../data";

const clockTime = new Intl.DateTimeFormat("id-ID", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Jakarta" });
const clockDate = new Intl.DateTimeFormat("id-ID", { weekday: "long", day: "numeric", month: "short", year: "numeric", timeZone: "Asia/Jakarta" });

export default function Navbar({ device, position, telemetry, telemetryOnline }) {
  const online = telemetryOnline ?? device.online;
  const hasTelemetry = Boolean(telemetry?.updatedAt || telemetry?.fix || telemetry?.terbaca);
  const tone = online ? "safe" : hasTelemetry ? "danger" : "idle";
  const label = online ? "Rompi online" : hasTelemetry ? "Rompi offline" : "Menunggu rompi";

  const [now, setNow] = useState(() => new Date());
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme || "light");

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 15000);
    return () => window.clearInterval(timer);
  }, []);

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.dataset.theme = next;
    try { window.localStorage.setItem("vc-theme", next); } catch { /* penyimpanan tidak tersedia */ }
  };

  return (
    <header className="vc-topbar">
      <div className="vc-shell vc-topbar-inner">
        <div className="vc-brand vc-brand--mobile">
          <img src={logo} alt="" />
          <div style={{ minWidth: 0 }}>
            <span className="vc-brand-name">Vest-Care</span>
            <span className="vc-brand-sub">{device.school || profile.sekolah}</span>
          </div>
        </div>
        <div className="vc-pagehead">
          <h1>Dashboard Monitoring</h1>
          <p>{device.school || profile.sekolah} · pemantauan rompi cerdas</p>
        </div>
        <div className="vc-topbar-right">
          <div className="vc-clock" aria-hidden="true">
            <b>{clockTime.format(now).replace(".", ":")} WIB</b>
            <span>{clockDate.format(now)}</span>
          </div>
          <span className={`vc-live vc-tone-${tone}`} data-live={online ? "true" : "false"} role="status">
            <span className="vc-dot" />
            <span className="vc-live-text">{label}</span>
          </span>
          <button
            type="button"
            className="vc-icon-btn"
            onClick={toggleTheme}
            aria-label={theme === "dark" ? "Ganti ke tema terang" : "Ganti ke tema gelap"}
            title={theme === "dark" ? "Tema terang" : "Tema gelap"}
          >
            <Icon name={theme === "dark" ? "sun" : "moon"} size={18} />
          </button>
          <ProfileMenu
            device={device}
            position={position}
            telemetry={telemetry}
            telemetryOnline={telemetryOnline}
          />
        </div>
      </div>
    </header>
  );
}
