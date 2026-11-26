import student from "../assets/img/student.png";
import { profile } from "../data";

export default function StudentCard({ device = {} }) {
  return (
    <div className="vc-student">
      <div className="vc-student-text">
        <h2>{device.studentName || profile.nama}</h2>
        <p>{device.school || profile.sekolah}</p>
      </div>
      <img src={student} alt="Siswa pengguna Vest-Care memakai rompi dan kacamata hitam" />
    </div>
  );
}
