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

export default function App() {
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

  function addDetections(newDetections) {
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
      <Sidebar device={device} online={telemetryOnline ?? device.online} />
      <div className="vc-main">
      <Navbar device={device} position={position} telemetry={telemetry} telemetryOnline={telemetryOnline} />
      <main className="vc-shell vc-page">
        <StatCards
          device={device}
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
            <StudentCard device={device} />
            <CategoryList detections={detections} />
          </div>
        </div>

        <DetectionHistory detections={history} />
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
