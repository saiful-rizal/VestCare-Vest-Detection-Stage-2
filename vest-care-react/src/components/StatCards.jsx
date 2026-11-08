import StatCard from "./StatCard";
import SubText from "./SubText";
import { COLOR, fmt } from "../data";

export default function StatCards({ device, detections, historyLoading, historyError }) {
  const { online, battery } = device;
  const d = detections[0];
  const bc = battery <= 20 ? COLOR.Tinggi : battery <= 50 ? COLOR.Sedang : COLOR.Rendah;
  const bLabel = battery <= 20 ? "Rendah" : battery <= 50 ? "Sedang" : "Baik";
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
        title="Baterai"
        value={battery == null ? "-" : `${battery}%`}
        sub={<SubText color={battery == null ? "#7a6460" : bc} strong={battery == null ? "Belum ada data" : bLabel}>kondisi baterai</SubText>}
        gradient="from-red-600 to-orange-600"
        icon="ni-active-40"
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
