export default function StatCard({ title, value, valueColor, sub, gradient, icon, last }) {
  return (
    <div className={`w-1/2 max-w-full px-3 flex-none xl:w-1/4 ${last ? "" : "mb-6 xl:mb-0"}`}>
      <div className="relative flex flex-col min-w-0 min-h-[160px] xl:min-h-0 break-words bg-white shadow-xl dark:bg-slate-850 dark:shadow-dark-xl rounded-2xl bg-clip-border">
        <div className="flex-auto p-4">
          <div className="flex items-start justify-between gap-2">
            <p className="mb-0 min-w-0 flex-1 font-sans text-[11px] font-semibold leading-normal uppercase dark:text-white dark:opacity-60 xl:text-xs">{title}</p>
            <div className={`flex h-9 w-9 flex-none items-center justify-center rounded-circle bg-gradient-to-tl ${gradient} xl:h-12 xl:w-12`}>
              <i className={`ni leading-none ${icon} text-base text-white xl:text-lg`}></i>
            </div>
          </div>
          <h5 className="mb-1 mt-2 text-base font-bold dark:text-white xl:text-lg" style={valueColor ? { color: valueColor } : undefined}>{value}</h5>
          <p className="mb-0 text-xs dark:text-white dark:opacity-60">{sub}</p>
        </div>
      </div>
    </div>
  );
}
