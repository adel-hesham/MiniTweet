import { useEffect, useState } from "react";

import { clearToken, getToken, me } from "./api";
import type { User } from "./api";
import AuthPanel from "./components/AuthPanel";
import Logo from "./components/Logo";
import MainArea from "./components/MainArea";
import Profile from "./components/Profile";
import SystemPanel from "./components/SystemPanel";
import ThemeToggle from "./components/ThemeToggle";

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState<boolean>(getToken() !== null);
  const [tab, setTab] = useState<"app" | "system">("app");

  // If there is a saved token, find out who it belongs to.
  useEffect(() => {
    if (getToken() === null) return;
    me()
      .then(setUser)
      .catch(() => clearToken())
      .finally(() => setChecking(false));
  }, []);

  function logout() {
    clearToken();
    setUser(null);
  }

  const tabClass = (active: boolean) =>
    `flex-1 py-3 text-sm font-semibold ${active ? "text-brand" : "opacity-60"}`;

  return (
    <div className="min-h-screen bg-surface pb-16 text-ink transition-colors dark:bg-surface-dark dark:text-ink-dark lg:pb-0">
      <header className="sticky top-0 z-10 border-b border-black/5 bg-surface/80 backdrop-blur dark:border-white/10 dark:bg-surface-dark/80">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
          <Logo />
          <ThemeToggle />
        </div>
      </header>

      <main className="mx-auto grid max-w-7xl gap-6 px-4 py-6 lg:grid-cols-2">
        <section className={tab === "app" ? "" : "hidden lg:block"}>
          {checking ? (
            <div className="h-48 animate-pulse rounded-2xl bg-black/5 dark:bg-white/10" />
          ) : user ? (
            <div className="space-y-4">
              <Profile user={user} onLogout={logout} />
              <MainArea user={user} />
            </div>
          ) : (
            <AuthPanel onAuthenticated={setUser} />
          )}
        </section>
        <section className={tab === "system" ? "" : "hidden lg:block"}>
          <SystemPanel />
        </section>
      </main>

      <nav className="fixed bottom-0 left-0 right-0 flex border-t border-black/10 bg-surface dark:border-white/10 dark:bg-surface-dark lg:hidden">
        <button className={tabClass(tab === "app")} onClick={() => setTab("app")}>
          App
        </button>
        <button className={tabClass(tab === "system")} onClick={() => setTab("system")}>
          System
        </button>
      </nav>
    </div>
  );
}
