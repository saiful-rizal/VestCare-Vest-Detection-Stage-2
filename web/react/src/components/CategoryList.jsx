import Icon, { OBJECT_ICON } from "./Icon";
import { fmt, toneOf } from "../data";

const NAMES = ["Lubang", "Mobil", "Motor", "Orang", "Pohon"];

export default function CategoryList({ detections }) {
  const high = detections.filter((d) => d.urgency === "Tinggi").length;

  return (
    <section className="vc-panel" id="objek" aria-labelledby="objek-title">
      <div className="vc-panel-head" style={{ paddingBottom: 6 }}>
        <div>
          <h2 className="vc-panel-title" id="objek-title">Objek di sekitar rompi</h2>
          <p className="vc-panel-sub">Dari deteksi terbaru</p>
        </div>
      </div>
      <ul className="vc-objects">
        {NAMES.map((name) => {
          const list = detections.filter((d) => d.object === name);
          const nearest = list.length ? list.reduce((a, b) => (b.distance < a.distance ? b : a)) : null;
          const tone = nearest ? toneOf(nearest) : "idle";
          return (
            <li key={name} className={`vc-object vc-tone-${tone}`} data-active={list.length > 0}>
              <span className="vc-object-icon"><Icon name={OBJECT_ICON[name]} size={18} /></span>
              <div>
                <p className="vc-object-name">{name}</p>
                <p className="vc-object-note">
                  {nearest ? `Terdekat ${fmt(nearest.distance)} m` : "Belum terdeteksi"}
                </p>
              </div>
              <span className="vc-object-count">{list.length}</span>
            </li>
          );
        })}
      </ul>
      <p className="vc-objects-sum">
        <span>Risiko tinggi</span>
        <strong>{high} dari {detections.length} deteksi</strong>
      </p>
    </section>
  );
}
