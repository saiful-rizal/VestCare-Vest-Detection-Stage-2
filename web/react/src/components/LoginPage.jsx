import { useState } from "react";
import { supabase } from "../supabaseClient";
import studentImage from "../assets/img/student.png";
import "../login.css";

const GOOGLE_OAUTH_REDIRECT_URL = "https://vestcare-detection-object-production.up.railway.app";

function GoogleMark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 48 48" width="17" height="17">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5Z" transform="translate(0 5)" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94a11.05 11.05 0 0 1-4.8 7.24l7.73 6C44.38 38.05 47 31.97 47 24.55Z" transform="translate(0 0)" />
      <path fill="#FBBC05" d="M10.53 28.41A14.4 14.4 0 0 1 9.75 24c0-1.53.27-3.01.75-4.41l-7.98-6.2A23.9 23.9 0 0 0 0 24c0 3.85.92 7.5 2.56 10.61l7.97-6.2Z" transform="translate(0 5)" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.9-5.8l-7.73-6c-2.14 1.44-4.88 2.3-8.17 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.2C6.51 42.62 14.62 48 24 48Z" transform="translate(0 -5)" />
    </svg>
  );
}

function getErrorMessage(error) {
  return error instanceof Error ? error.message : String(error);
}

function getGoogleErrorMessage(error) {
  const message = getErrorMessage(error);
  if (/unsupported provider|provider.{0,80}(not enabled|disabled)/i.test(message)) {
    return "Login Google belum aktif di Supabase. Aktifkan provider Google dan masukkan Client ID/Secret di Authentication > Sign In / Providers.";
  }
  return message;
}

export default function LoginPage({ initialError = "" }) {
  const [mode, setMode] = useState("login");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [message, setMessage] = useState(initialError);
  const [isError, setIsError] = useState(Boolean(initialError));
  const [submitting, setSubmitting] = useState(false);

  function showMessage(text, error = false) {
    setMessage(text);
    setIsError(error);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!supabase) {
      showMessage("Autentikasi belum dikonfigurasi. Isi URL dan publishable key Supabase di environment frontend.", true);
      return;
    }

    const normalizedEmail = email.trim().toLowerCase();
    const normalizedFullName = fullName.trim();
    if (mode === "signup" && !normalizedFullName) {
      showMessage("Masukkan nama siswa terlebih dahulu.", true);
      return;
    }

    setSubmitting(true);
    showMessage("");
    try {
      const result = mode === "signup"
        ? await supabase.auth.signUp({
          email: normalizedEmail,
          password,
          options: { data: { full_name: normalizedFullName } },
        })
        : await supabase.auth.signInWithPassword({ email: normalizedEmail, password });

      if (result.error) throw result.error;
      if (mode === "signup" && !result.data.session) {
        showMessage("Akun berhasil dibuat. Periksa email Anda untuk mengonfirmasi pendaftaran.");
      }
    } catch (error) {
      showMessage(getErrorMessage(error), true);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleGoogleSignIn() {
    if (!supabase) {
      showMessage("Autentikasi belum dikonfigurasi. Isi URL dan publishable key Supabase di environment frontend.", true);
      return;
    }

    setSubmitting(true);
    showMessage("");
    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: { redirectTo: GOOGLE_OAUTH_REDIRECT_URL },
      });
      if (error) throw error;
    } catch (error) {
      showMessage(getGoogleErrorMessage(error), true);
      setSubmitting(false);
    }
  }

  async function handleGuestSignIn() {
    if (!supabase) {
      showMessage("Autentikasi belum dikonfigurasi. Isi URL dan publishable key Supabase di environment frontend.", true);
      return;
    }

    setSubmitting(true);
    showMessage("");
    try {
      const { error } = await supabase.auth.signInAnonymously();
      if (
        error?.code === "anonymous_provider_disabled"
        || error?.message?.toLowerCase().includes("anonymous sign-ins are disabled")
      ) {
        throw new Error("Login tamu belum aktif. Aktifkan Anonymous Sign-Ins di pengaturan Authentication Supabase.");
      }
      if (error) throw error;
    } catch (error) {
      showMessage(getErrorMessage(error), true);
    } finally {
      setSubmitting(false);
    }
  }

  async function handlePasswordReset() {
    if (!supabase) {
      showMessage("Autentikasi belum dikonfigurasi. Isi URL dan publishable key Supabase di environment frontend.", true);
      return;
    }
    if (!email.trim()) {
      showMessage("Masukkan alamat email terlebih dahulu untuk menerima tautan reset kata sandi.", true);
      return;
    }

    setSubmitting(true);
    showMessage("");
    try {
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: window.location.origin,
      });
      if (error) throw error;
      showMessage("Jika email terdaftar, tautan untuk mengatur ulang kata sandi akan segera dikirim.");
    } catch (error) {
      showMessage(getErrorMessage(error), true);
    } finally {
      setSubmitting(false);
    }
  }

  const isSignup = mode === "signup";

  return (
    <main className="vc-login-page">
      <section className="vc-login-card" aria-label="Masuk ke VestCare">
        <aside className="vc-login-showcase">
          <div className="vc-login-grid" aria-hidden="true" />
          <div className="vc-login-orbit vc-login-orbit--one" aria-hidden="true" />
          <div className="vc-login-orbit vc-login-orbit--two" aria-hidden="true" />
          <div className="vc-login-photo-wrap">
            <img
              className="vc-login-student"
              src={studentImage}
              alt="Siswa mengenakan rompi VestCare"
            />
            <div className="vc-login-photo-shade" />
            <div className="vc-login-brand">
              <img src="/favicon.png" alt="" />
              <div>
                <strong>VestCare</strong>
                <span>Rompi cerdas, perlindungan lebih baik.</span>
              </div>
            </div>
            <div className="vc-login-showcase-caption">
              <span className="vc-login-status-dot" />
              <span>Keselamatan siswa, dalam pantauan.</span>
            </div>
          </div>
        </aside>

        <div className="vc-login-content">
          <div className="vc-login-mobile-brand">
            <img src="/favicon.png" alt="" />
            <span>VestCare</span>
          </div>
          <div className="vc-login-heading">
            <span className="vc-login-eyebrow">PORTAL MONITORING</span>
            <h1>{isSignup ? "Buat akun baru" : "Selamat datang kembali"}</h1>
            <p>{isSignup ? "Daftar untuk mulai memantau keselamatan." : "Masuk untuk melanjutkan ke dashboard VestCare."}</p>
          </div>

          <form className="vc-login-form" onSubmit={handleSubmit}>
            {isSignup && (
              <>
                <label htmlFor="vc-login-full-name">Nama siswa</label>
                <div className="vc-login-input-wrap">
                  <svg aria-hidden="true" viewBox="0 0 24 24">
                    <circle cx="12" cy="8" r="4" />
                    <path d="M4 21a8 8 0 0 1 16 0" />
                  </svg>
                  <input
                    autoComplete="name"
                    id="vc-login-full-name"
                    name="fullName"
                    onChange={(event) => setFullName(event.target.value)}
                    placeholder="Nama lengkap siswa"
                    required
                    type="text"
                    value={fullName}
                  />
                </div>
              </>
            )}
            <label htmlFor="vc-login-email">Alamat email</label>
            <div className="vc-login-input-wrap">
              <svg aria-hidden="true" viewBox="0 0 24 24">
                <rect x="3" y="5" width="18" height="14" rx="3" />
                <path d="m4 7 8 6 8-6" />
              </svg>
              <input
                autoComplete="email"
                id="vc-login-email"
                name="email"
                onChange={(event) => setEmail(event.target.value)}
                placeholder="nama@email.com"
                required
                type="email"
                value={email}
              />
            </div>

            <div className="vc-login-password-label">
              <label htmlFor="vc-login-password">Kata sandi</label>
              {!isSignup && (
                <button className="vc-login-text-button" disabled={submitting} onClick={handlePasswordReset} type="button">
                  Lupa kata sandi?
                </button>
              )}
            </div>
            <div className="vc-login-input-wrap">
              <svg aria-hidden="true" viewBox="0 0 24 24">
                <rect x="4" y="10" width="16" height="11" rx="3" />
                <path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2" />
              </svg>
              <input
                autoComplete={isSignup ? "new-password" : "current-password"}
                id="vc-login-password"
                minLength={6}
                name="password"
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Minimal 6 karakter"
                required
                type={passwordVisible ? "text" : "password"}
                value={password}
              />
              <button
                aria-label={passwordVisible ? "Sembunyikan kata sandi" : "Tampilkan kata sandi"}
                aria-pressed={passwordVisible}
                className="vc-login-password-toggle"
                onClick={() => setPasswordVisible((visible) => !visible)}
                title={passwordVisible ? "Sembunyikan kata sandi" : "Tampilkan kata sandi"}
                type="button"
              >
                <svg aria-hidden="true" viewBox="0 0 24 24">
                  {passwordVisible ? (
                    <>
                      <path d="m3 3 18 18M10.6 10.6a2 2 0 0 0 2.8 2.8" />
                      <path d="M9.9 5.2A10.7 10.7 0 0 1 12 5c6.5 0 10 7 10 7a15.4 15.4 0 0 1-3.1 3.8M6.2 6.2C3.5 8.1 2 12 2 12s3.5 7 10 7c1.4 0 2.7-.4 3.8-1" />
                    </>
                  ) : (
                    <>
                      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" />
                      <circle cx="12" cy="12" r="3" />
                    </>
                  )}
                </svg>
              </button>
            </div>

            {message && (
              <p className={`vc-login-message${isError ? " is-error" : ""}`} role={isError ? "alert" : "status"}>
                {message}
              </p>
            )}

            <button className="vc-login-submit" disabled={submitting} type="submit">
              {submitting ? "Memproses..." : isSignup ? "Buat akun" : "Masuk dengan email"}
            </button>
          </form>

          <div className="vc-login-divider"><span>atau lanjutkan dengan</span></div>
          <button className="vc-login-google" disabled={submitting} onClick={handleGoogleSignIn} type="button">
            <GoogleMark />
            <span>Lanjutkan dengan Google</span>
          </button>
          <button className="vc-login-guest" disabled={submitting} onClick={handleGuestSignIn} type="button">
            <svg aria-hidden="true" viewBox="0 0 24 24">
              <circle cx="12" cy="8" r="3.5" />
              <path d="M5 20a7 7 0 0 1 14 0" />
            </svg>
            <span>Masuk sebagai tamu</span>
          </button>
          <p className="vc-login-guest-note">Tanpa email atau ID; dashboard tetap realtime.</p>

          <p className="vc-login-switch">
            {isSignup ? "Sudah punya akun?" : "Belum punya akun?"}{" "}
            <button
              className="vc-login-text-button"
              onClick={() => {
                setMode(isSignup ? "login" : "signup");
                showMessage("");
              }}
              type="button"
            >
              {isSignup ? "Masuk" : "Daftar sekarang"}
            </button>
          </p>
          <p className="vc-login-footer">© {new Date().getFullYear()} VestCare · Monitoring Rompi Cerdas</p>
        </div>
      </section>
    </main>
  );
}
