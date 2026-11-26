import { useEffect, useState } from "react";
import { supabase } from "./supabaseClient";
import LoginPage from "./components/LoginPage";

export default function AuthGate({ children }) {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(Boolean(supabase));
  const [error, setError] = useState("");

  useEffect(() => {
    if (!supabase) return undefined;

    let active = true;
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
      setLoading(false);
    });

    supabase.auth.getSession()
      .then(({ data, error: sessionError }) => {
        if (!active) return;
        if (sessionError) setError(sessionError.message);
        else setSession(data.session);
        setLoading(false);
      })
      .catch((sessionError) => {
        if (!active) return;
        setError(sessionError instanceof Error ? sessionError.message : String(sessionError));
        setLoading(false);
      });

    return () => {
      active = false;
      subscription.unsubscribe();
    };
  }, []);

  if (!supabase) {
    return (
      <LoginPage initialError="Autentikasi belum dikonfigurasi. Isi URL dan publishable key Supabase di environment frontend." />
    );
  }
  if (loading) {
    return (
      <div className="vc-auth-loading" role="status" aria-live="polite">
        Memeriksa sesi akun...
      </div>
    );
  }
  if (!session) return <LoginPage initialError={error} />;
  return children;
}
