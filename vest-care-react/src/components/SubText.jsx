// Teks kecil berwarna + keterangan, mis. "0,8 m jarak objek"
export default function SubText({ color, strong, children }) {
  return (
    <>
      <span className="text-sm font-bold leading-normal" style={{ color }}>{strong}</span> {children}
    </>
  );
}
