import student from "../assets/img/student.png";

export default function StudentCard() {
  return (
    <div className="w-full max-w-full px-3 lg:w-5/12 lg:flex-none">
      <div className="vc-student">
        <div className="vc-student-text"><h5>Vest-Care</h5><p>Teman Netra</p></div>
        <img src={student} alt="Siswa pengguna Vest-Care memakai rompi dan kacamata hitam" />
      </div>
    </div>
  );
}
