import { useEffect, useState } from "react";
import Icon from "./Icon";
import logo from "../assets/img/favicon.png";
import { profile } from "../data";

// Navigasi antar-bagian pada halaman dashboard (hanya scroll, tanpa routing).
const ITEMS = [
  { id: "ringkasan", label: "Ringkasan", short: "Ringkasan", icon: "pulse" },
  { id: "peta", label: "Lokasi & Sensor", short: "Lokasi", icon: "pin" },
  { id: "objek", label: "Objek Terdeteksi", short: "Objek", icon: "camera" },
  { id: "riwayat", label: "Riwayat Deteksi", short: "Riwayat", icon: "clock" },
];

export default function Sidebar({ device, online }) {
  const [collapsed, setCollapsed] = useState(false);
  const [active, setActive] = useState(ITEMS[0].id);

  // Tandai menu aktif sesuai bagian yang sedang tampil.
  useEffect(() => {
    const sections = ITEMS.map((item) => document.getElementById(item.id)).filter(Boolean);
    if (!sections.length || typeof IntersectionObserver === "undefined") return undefined;
    const observer = new IntersectionObserver(
      (entries) => entries.forEach((entry) => { if (entry.isIntersecting) setActive(entry.target.id); }),
      { rootMargin: "-25% 0px -60% 0px" },
    );
    sections.forEach((section) => observer.observe(section));
    return () => observer.disconnect();
  }, []);

  const go = (event, id) => {
    event.preventDefault();
    setActive(id);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <aside className="vc-sidebar" data-collapsed={collapsed} aria-label="Navigasi utama">
      <div className="vc-side-brand">
        <img src={logo} alt="" />
        <div>
          <b>Vest-Care</b>
          <span>Smart safety monitoring</span>
        </div>
      </div>

      <p className="vc-side-label">MENU</p>
      <nav className="vc-nav">
        {ITEMS.map((item) => (
          <a
            key={item.id}
            href={`#${item.id}`}
            aria-current={active === item.id ? "true" : undefined}
            title={collapsed ? item.label : undefined}
            onClick={(event) => go(event, item.id)}
          >
            <Icon name={item.icon} size={19} />
            <span>
              <span className="vc-nav-long">{item.label}</span>
              <span className="vc-nav-short">{item.short}</span>
            </span>
          </a>
        ))}
      </nav>

      <div className="vc-side-foot">
        <div className={`vc-side-status vc-tone-${online ? "safe" : "idle"}`}>
          <span className="vc-dot" style={{ boxShadow: online ? "0 0 0 4px rgba(34,197,94,.2)" : "none" }} />
          <div>
            <b>{device.name || profile.perangkat}</b>
            <span className="s">{online ? "Online" : "Offline"}</span>
          </div>
        </div>
        <button
          type="button"
          className="vc-side-toggle"
          onClick={() => setCollapsed((value) => !value)}
          aria-label={collapsed ? "Perluas sidebar" : "Ciutkan sidebar"}
          aria-pressed={collapsed}
        >
          <Icon name="panel" size={19} />
          <span>{collapsed ? "Perluas" : "Ciutkan"}</span>
        </button>
      </div>
    </aside>
  );
}
