import { useEffect, useRef, useState } from "react";
import avatar from "../assets/img/avatar.png";
import { COLOR, profile } from "../data";

export default function ProfileMenu({ device, position }) {
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
            <div><b>{profile.nama}</b><span>{profile.sekolah}</span></div>
          </div>
          <div className="vc-row"><span>Perangkat</span><span>{profile.perangkat}</span></div>
          <div className="vc-row">
            <span>Status rompi</span>
            <span>
              <span className="vc-dot" style={{ background: device.online ? COLOR.Rendah : "#9a8b88" }}></span>
              {device.online ? "Online" : "Offline"}
            </span>
          </div>
          <div className="vc-row"><span>Baterai</span><span>{device.battery}%</span></div>
          <div className="vc-row"><span>Lokasi terakhir</span><span>{position.lat.toFixed(5)}, {position.lng.toFixed(5)}</span></div>
        </div>
      )}
    </li>
  );
}
