import { useContext, useRef, useState } from "react";
import { AuthContext } from "./AuthGate";
import Navbar from "./components/Navbar";
import Sidebar from "./components/Sidebar";
import StatCards from "./components/StatCards";
import GpsMap from "./components/GpsMap";
import StudentCard from "./components/StudentCard";
import DetectionHistory from "./components/DetectionHistory";
import CategoryList from "./components/CategoryList";
import Footer from "./components/Footer";
import CameraCapture from "./components/CameraCapture";
import useVestData from "./useVestData";

function getLoginDisplayName(user) {
  const metadata = user?.user_metadata || {};
  const metadataName = [metadata.full_name, metadata.name, metadata.user_name]
    .find((name) => typeof name === "string" && name.trim());
  if (metadataName) return metadataName.trim();
  return typeof user?.email === "string" ? user.email.split("@")[0].trim() : "";
}

export default function App() {
  const user = useContext(AuthContext);
  const [realtimeHistory, setRealtimeHistory] = useState([]);
  const activeRealtimeEventsRef = useRef(new Map());
  const realtimeHistorySequenceRef = useRef(0);
  const [{
    device,
    position,
    detections,
    history,
    telemetry,
    telemetryOnline,
    trail,
    mapConfig,
    detectionHistoryLoading,
    detectionHistoryError,
  }, setState] = useVestData();
  const loginName = getLoginDisplayName(user);
  const displayDevice = loginName ? { ...device, studentName: loginName } : device;
  const displayedHistory = [...realtimeHistory, ...history].slice(0, 20);

  function addDetections(newDetections, { realtime = true } = {}) {
    if (realtime) {
      const previousEvents = activeRealtimeEventsRef.current;
      const nextEvents = new Map();
      const fallbackOccurrences = new Map();
      const liveRows = newDetections.filter((detection) => !detection.ragu).map((detection) => {
        let identity;
        if (Number.isFinite(detection.id)) {
          identity = `${detection.object}#${detection.id}`;
        } else {
          const base = `${detection.object}|${detection.arah || ""}|${detection.level}`;
          const occurrence = fallbackOccurrences.get(base) || 0;
          fallbackOccurrences.set(base, occurrence + 1);
          identity = `${base}|${occurrence}`;
        }

        const eventKey = `${identity}|${detection.arah || ""}|${detection.level}`;
        const liveHistoryId = previousEvents.get(eventKey)
          || `live-${Date.now()}-${++realtimeHistorySequenceRef.current}`;
        nextEvents.set(eventKey, liveHistoryId);
        return { ...detection, liveHistoryId };
      });

      activeRealtimeEventsRef.current = nextEvents;
      setRealtimeHistory((current) => {
        const liveById = new Map(liveRows.map((row) => [row.liveHistoryId, row]));
        const currentIds = new Set(current.map((row) => row.liveHistoryId));
        let changed = false;
        const updated = current.map((row) => {
          const liveRow = liveById.get(row.liveHistoryId);
          if (!liveRow) return row;
          if (
            row.time === liveRow.time
            && row.distance === liveRow.distance
            && row.confidence === liveRow.confidence
          ) {
            return row;
          }
          changed = true;
          return { ...row, ...liveRow };
        });
        const added = liveRows.filter((row) => !currentIds.has(row.liveHistoryId));
        if (!changed && !added.length) return current;
        return [...added, ...updated].slice(0, 20);
      });
    } else {
      activeRealtimeEventsRef.current = new Map();
    }

    setState((state) => ({
      ...state,
      detections: newDetections,
      detectionsUpdatedAt: Date.now(),
      detectionHistoryLoading: false,
      detectionHistoryError: null,
    }));
  }

  return (
    <div className="vc-app">
      <Sidebar device={displayDevice} online={telemetryOnline ?? device.online} />
      <div className="vc-main">
      <Navbar device={displayDevice} position={position} telemetry={telemetry} telemetryOnline={telemetryOnline} />
      <main className="vc-shell vc-page">
        <StatCards
          device={displayDevice}
          detections={detections}
          telemetry={telemetry}
          telemetryOnline={telemetryOnline}
          historyLoading={detectionHistoryLoading}
          historyError={detectionHistoryError}
        />

        <div className="vc-grid">
          <GpsMap
            position={position}
            detections={detections}
            telemetry={telemetry}
            trail={trail}
            mapConfig={mapConfig}
          />
          <div className="vc-side">
            <StudentCard device={displayDevice} />
            <CategoryList detections={detections} />
          </div>
        </div>

        <DetectionHistory detections={displayedHistory} />
        <Footer />
      </main>
      </div>
      <CameraCapture
        onDetections={addDetections}
        deviceOnline={telemetryOnline ?? device.online}
        lastSeen={telemetry?.updatedAt}
      />
    </div>
  );
}
