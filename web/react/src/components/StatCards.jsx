import StatCard from "./StatCard";
import SubText from "./SubText";
import { COLOR, fmt } from "../data";

export default function StatCards({ device, detections, telemetry, telemetryOnline, historyLoading, historyError }) {
  const online = telemetryOnline ?? device.online;
  const distance = telemetry?.jarak ?? null;
  const distanceColor = distance == null
    ? "#7a6460"
    : distance < 1
      ? COLOR.Tinggi
      : distance < 2
        ? COLOR.Sedang
        : COLOR.Rendah;
  const distanceLabel = distance == null
    ? telemetry?.terbaca
      ? "Di luar jangkauan"
      : "Menunggu Wemos"
    : distance < 1
      ? "Sangat dekat"
      : distance < 2
        ? "Dekat"
        : "Aman";
  const d = detections[0];
  const levelColors = { BAHAYA: COLOR.Tinggi, WASPADA: COLOR.Sedang, INFO: COLOR.Rendah, AMAN: COLOR.Rendah };
  const urgency = d?.level || d?.urgency?.toUpperCase() || "-";
  const urgencyColor = levelColors[urgency] || COLOR[d?.urgency] || COLOR.Sedang;
  const detectionStatus = historyError
    ? <span className="text-xs text-red-600">{historyError}</span>
    : historyLoading
      ? "Memuat riwayat server"
      : "Belum ada deteksi";

  return (
    <div className="flex flex-wrap -mx-3">
      <StatCard
        title="Status perangkat"
        value={online ? "Online" : "Offline"}
        sub={online ? <SubText color={COLOR.Rendah} strong="Aktif">mengirim data</SubText> : <SubText color="#7a6460" strong="Terputus">tidak ada data</SubText>}
        gradient="from-blue-500 to-violet-500"
        icon="ni-button-power"
      />
      <StatCard
        title="Jarak sensor"
        value={distance == null ? "-" : `${fmt(distance)} m`}
        sub={<SubText color={distanceColor} strong={distanceLabel}>ultrasonik depan</SubText>}
        gradient="from-red-600 to-orange-600"
        icon="ni-sound-wave"
      />
      <StatCard
        title="Deteksi terakhir"
        value={d?.object || "-"}
        sub={d ? <SubText color={urgencyColor} strong={`${fmt(d.distance)} m`}>jarak objek</SubText> : detectionStatus}
        gradient="from-emerald-500 to-teal-400"
        icon="ni-camera-compact"
      />
      <StatCard
        last
        title="Urgensi"
        value={d ? urgency : "-"}
        valueColor={d && urgencyColor}
        sub={d ? <SubText color={urgencyColor} strong={`${Math.round(d.confidence)}%`}>confidence</SubText> : detectionStatus}
        gradient="from-orange-500 to-yellow-500"
        icon="ni-bell-55"
      />
    </div>
  );
}
