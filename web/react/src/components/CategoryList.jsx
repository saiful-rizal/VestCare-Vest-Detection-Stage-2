import { fmt } from "../data";

const NAMES = [
  { name: "Lubang", icon: "ni-support-16" },
  { name: "Mobil", icon: "ni-delivery-fast" },
  { name: "Motor", icon: "ni-bus-front-12" },
  { name: "Orang", icon: "ni-satisfied" },
  { name: "Pohon", icon: "ni-world-2" },
];

function Item({ icon, title, children, last }) {
  return (
    <li className={`relative flex justify-between py-2 pr-4 ${last ? "" : "mb-2"} border-0 rounded-xl text-inherit`}>
      <div className="flex items-center">
        <div className="inline-block w-8 h-8 mr-4 text-center text-black bg-center shadow-sm fill-current stroke-none bg-gradient-to-tl from-zinc-800 to-zinc-700 dark:bg-gradient-to-tl dark:from-slate-750 dark:to-gray-850 rounded-xl">
          <i className={`text-white ni ${icon} relative top-0.75 text-xxs`}></i>
        </div>
        <div className="flex flex-col">
          <h6 className="mb-1 text-sm leading-normal text-slate-700 dark:text-white">{title}</h6>
          <span className="text-xs leading-tight dark:text-white/80">{children}</span>
        </div>
      </div>
      <div className="flex">
        <button className="group ease-in leading-pro text-xs rounded-3.5xl p-1.2 h-6.5 w-6.5 mx-0 my-auto inline-block cursor-pointer border-0 bg-transparent text-center align-middle font-bold text-slate-700 shadow-none transition-all dark:text-white">
          <i className="ni ease-bounce text-2xs group-hover:translate-x-1.25 ni-bold-right transition-all duration-200" aria-hidden="true"></i>
        </button>
      </div>
    </li>
  );
}

export default function CategoryList({ detections }) {
  const high = detections.filter((d) => d.urgency === "Tinggi").length;
  return (
    <div className="w-full max-w-full px-3 mt-0 lg:w-5/12 lg:flex-none">
      <div className="border-black/12.5 shadow-xl dark:bg-slate-850 dark:shadow-dark-xl relative flex min-w-0 flex-col break-words rounded-2xl border-0 border-solid bg-white bg-clip-border">
        <div className="p-4 pb-0 rounded-t-4">
          <h6 className="mb-0 dark:text-white">Jumlah per objek</h6>
        </div>
        <div className="flex-auto p-4">
          <ul className="flex flex-col pl-0 mb-0 rounded-lg">
            {NAMES.map(({ name, icon }) => {
              const l = detections.filter((d) => d.object === name);
              return (
                <Item key={name} icon={icon} title={name}>
                  {l.length ? (
                    <>{l.length} deteksi, <span className="font-semibold">terdekat {fmt(Math.min(...l.map((x) => x.distance)))} m</span></>
                  ) : "Belum ada deteksi"}
                </Item>
              );
            })}
            <Item last icon="ni-bell-55" title="Urgensi tinggi">
              {high} deteksi, <span className="font-semibold">dari {detections.length} total</span>
            </Item>
          </ul>
        </div>
      </div>
    </div>
  );
}
