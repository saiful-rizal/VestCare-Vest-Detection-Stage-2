import { useEffect } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from "react-leaflet";
import { COLOR, fmt } from "../data";

// Geser peta setiap posisi rompi berubah
function PanTo({ position }) {
  const map = useMap();
  useEffect(() => { map.panTo([position.lat, position.lng]); }, [map, position.lat, position.lng]);
  return null;
}

export default function GpsMap({ position, detections }) {
  return (
    <div className="w-full max-w-full px-3 mt-0 lg:w-7/12 lg:flex-none">
      <div className="border-black/12.5 dark:bg-slate-850 dark:shadow-dark-xl shadow-xl relative z-20 flex min-w-0 flex-col break-words rounded-2xl border-0 border-solid bg-white bg-clip-border">
        <div className="border-black/12.5 mb-0 rounded-t-2xl border-b-0 border-solid p-6 pt-4 pb-0">
          <h6 className="capitalize dark:text-white">Lokasi GPS</h6>
          <p className="mb-0 text-sm leading-normal dark:text-white dark:opacity-60">
            <i className="ni ni-pin-3" style={{ color: "#660f08" }}></i>{" "}
            <span className="font-semibold">
              {position.lat.toFixed(5)}, {position.lng.toFixed(5)} - diperbarui {position.updated}
            </span>
          </p>
        </div>
        <div className="flex-auto p-4">
          <MapContainer center={[position.lat, position.lng]} zoom={17} style={{ height: 340, borderRadius: 12 }}>
            <TileLayer
              url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
              maxZoom={19}
              attribution="&copy; OpenStreetMap"
            />
            {detections.filter((d) => d.lat != null).map((d, i) => (
              <CircleMarker
                key={i}
                center={[d.lat, d.lng]}
                radius={7}
                pathOptions={{ color: "#fff", weight: 2, fillColor: COLOR[d.urgency], fillOpacity: 1 }}
              >
                <Popup><b>{d.object}</b><br />{fmt(d.distance)} m, {d.urgency}<br />{d.time}</Popup>
              </CircleMarker>
            ))}
            <CircleMarker
              center={[position.lat, position.lng]}
              radius={11}
              pathOptions={{ color: "#fff", weight: 3, fillColor: "#660f08", fillOpacity: 1 }}
            >
              <Popup>Posisi rompi</Popup>
            </CircleMarker>
            <PanTo position={position} />
          </MapContainer>
        </div>
      </div>
    </div>
  );
}
