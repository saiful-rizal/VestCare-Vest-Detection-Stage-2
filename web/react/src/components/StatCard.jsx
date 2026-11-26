// Satu ukuran (KPI) pada panel ringkasan.
export default function StatCard({ label, icon, value, tone, note, children }) {
  return (
    <div className={`vc-kpi ${tone ? `vc-tone-${tone}` : ""}`}>
      <p className="vc-kpi-label">{icon}{label}</p>
      <div className="vc-kpi-value" data-tone={tone || undefined}>{value}</div>
      {note && <p className="vc-kpi-note">{note}</p>}
      {children}
    </div>
  );
}
