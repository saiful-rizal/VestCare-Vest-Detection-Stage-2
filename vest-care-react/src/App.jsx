import Navbar from "./components/Navbar";
import StatCards from "./components/StatCards";
import GpsMap from "./components/GpsMap";
import StudentCard from "./components/StudentCard";
import DetectionHistory from "./components/DetectionHistory";
import CategoryList from "./components/CategoryList";
import Footer from "./components/Footer";
import CameraCapture from "./components/CameraCapture";
import useVestData from "./useVestData";

export default function App() {
  const [{ device, position, detections, history, detectionHistoryLoading, detectionHistoryError }, setState] = useVestData();

  function addDetections(newDetections) {
    setState((state) => ({
      ...state,
      detections: newDetections,
      detectionHistoryLoading: false,
      detectionHistoryError: null,
    }));
  }

  return (
    <>
      <div className="absolute w-full dark:hidden min-h-75" style={{ background: "linear-gradient(to top,#ffffff 0%,#660f08 75%)" }}></div>
      <main className="relative h-full max-h-screen transition-all duration-200 ease-in-out rounded-xl">
        <Navbar device={device} position={position} />
        <div className="w-full px-6 py-6 mx-auto">
          <StatCards
            device={device}
            detections={detections}
            historyLoading={detectionHistoryLoading}
            historyError={detectionHistoryError}
          />
          <div className="flex flex-wrap mt-6 -mx-3">
            <GpsMap position={position} detections={detections} />
            <StudentCard />
          </div>
          <div className="flex flex-wrap mt-6 -mx-3">
            <DetectionHistory detections={history} />
            <CategoryList detections={detections} />
          </div>
          <Footer />
        </div>
      </main>
      <CameraCapture onDetections={addDetections} />
    </>
  );
}
