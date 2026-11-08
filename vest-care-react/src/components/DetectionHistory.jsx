import { COLOR, ICON, fmt } from "../data";

const TD = "p-2 align-middle bg-transparent border-b whitespace-nowrap dark:border-white/40";
const LBL = "mb-0 text-xs font-semibold leading-tight dark:text-white dark:opacity-60";
const VAL = "mb-0 text-sm leading-normal dark:text-white";

function Cell({ label, children, color }) {
  return (
    <td className={TD}>
      <div className="text-center">
        <p className={LBL}>{label}</p>
        <h6 className={VAL} style={color ? { color } : undefined}>{children}</h6>
      </div>
    </td>
  );
}

export default function DetectionHistory({ detections }) {
  return (
    <div className="w-full max-w-full px-3 mt-0 mb-6 lg:mb-0 lg:w-7/12 lg:flex-none">
      <div className="relative flex flex-col min-w-0 break-words bg-white border-0 border-solid shadow-xl dark:bg-slate-850 dark:shadow-dark-xl rounded-2xl bg-clip-border">
        <div className="p-4 pb-0 mb-0 rounded-t-4">
          <h6 className="mb-2 dark:text-white">Riwayat deteksi</h6>
        </div>
        <div className="overflow-x-auto">
          <table className="items-center w-full mb-4 align-top border-collapse border-gray-200 dark:border-white/40">
            <tbody>
              {detections.map((d, i) => (
                <tr key={i}>
                  <td className={`${TD} w-3/10`}>
                    <div className="flex items-center px-2 py-1">
                      <div className="inline-block w-8 h-8 text-center rounded-xl" style={{ background: COLOR[d.urgency] }}>
                        <i className={`ni ${ICON[d.object] || "ni-bell-55"} text-white relative top-0.75 text-xxs`}></i>
                      </div>
                      <div className="ml-6"><p className={LBL}>Objek:</p><h6 className={VAL}>{d.object}</h6></div>
                    </div>
                  </td>
                  <Cell label="Waktu:">{d.time}</Cell>
                  <Cell label="Jarak:">{fmt(d.distance)} m</Cell>
                  <Cell label="Urgensi:" color={COLOR[d.urgency]}>{d.urgency}</Cell>
                </tr>
              ))}
              {!detections.length && (
                <tr><td className={`${TD} text-center text-sm text-slate-500`} colSpan={4}>Belum ada riwayat deteksi.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
