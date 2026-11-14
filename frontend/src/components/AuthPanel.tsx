import { useState } from "react";
import type { FormEvent } from "react";

import { login, me, register, setToken } from "../api";
import type { User } from "../api";

interface Props {
  onAuthenticated: (user: User) => void;
}

const inputClass =
  "w-full rounded-xl border border-black/10 bg-white px-4 py-3 text-sm outline-none transition " +
  "focus:border-brand focus:ring-2 focus:ring-brand/30 dark:border-white/10 dark:bg-surface-dark";

export default function AuthPanel({ onAuthenticated }: Props) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (mode === "register") await register(username, password);
      const { access_token } = await login(username, password);
      setToken(access_token);
      onAuthenticated(await me());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  const tab = (active: boolean) =>
    `flex-1 rounded-lg py-2 text-sm font-semibold transition ${
      active ? "bg-brand text-white shadow" : "opacity-70 hover:opacity-100"
    }`;

  return (
    <div className="rounded-2xl border border-black/5 bg-card p-6 shadow-sm dark:border-white/10 dark:bg-card-dark">
      <h2 className="text-2xl font-extrabold tracking-tight">
        {mode === "login" ? "Welcome back" : "Create your account"}
      </h2>
      <p className="mt-1 text-sm opacity-70">
        {mode === "login" ? "Log in to start tweeting." : "It takes a few seconds."}
      </p>

      <div className="mt-5 flex gap-1 rounded-xl bg-black/5 p-1 dark:bg-white/10">
        <button type="button" className={tab(mode === "login")} onClick={() => setMode("login")}>
          Log in
        </button>
        <button type="button" className={tab(mode === "register")} onClick={() => setMode("register")}>
          Sign up
        </button>
      </div>

      <form onSubmit={submit} className="mt-5 space-y-4">
        <input
          className={inputClass}
          placeholder="Username"
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
        />
        <input
          className={inputClass}
          type="password"
          placeholder="Password"
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        {mode === "register" && (
          <p className="text-xs opacity-60">3 to 20 letters, numbers or _ . Password: 6 or more characters.</p>
        )}
        {error && (
          <div className="rounded-xl bg-red-100 px-4 py-2 text-sm text-red-700 dark:bg-red-900/40 dark:text-red-300">
            {error}
          </div>
        )}
        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-xl bg-brand py-3 text-sm font-semibold text-white transition hover:bg-brand-dark disabled:opacity-60"
        >
          {busy ? "Please wait..." : mode === "login" ? "Log in" : "Create account"}
        </button>
      </form>
    </div>
  );
}
