import { decodeToken, getToken } from "../api";
import type { User } from "../api";

interface Props {
  user: User;
  onLogout: () => void;
}

export default function Profile({ user, onLogout }: Props) {
  const token = getToken() ?? "";
  const claims = decodeToken(token);
  const exp = claims && typeof claims.exp === "number" ? claims.exp : null;

  return (
    <div className="rounded-2xl border border-black/5 bg-card p-5 shadow-sm dark:border-white/10 dark:bg-card-dark">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-gradient-to-br from-brand to-accent text-xl font-bold uppercase text-white">
            {user.username.charAt(0)}
          </div>
          <div>
            <h2 className="text-lg font-extrabold tracking-tight">@{user.username}</h2>
            <p className="text-xs opacity-70">User #{user.id}</p>
          </div>
        </div>
        <button
          onClick={onLogout}
          className="rounded-full border border-black/10 px-4 py-2 text-sm font-semibold transition hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10"
        >
          Log out
        </button>
      </div>

      <details className="mt-4">
        <summary className="cursor-pointer text-xs font-semibold opacity-70">Show my login token</summary>
        <p className="mt-2 text-xs opacity-70">
          This is what user-service gave you. Every other service checks it the same way.
          {exp !== null && ` Expires at ${new Date(exp * 1000).toLocaleTimeString()}.`}
        </p>
        <pre className="mt-2 overflow-x-auto rounded-xl bg-black/5 p-3 text-xs dark:bg-white/10">
          {JSON.stringify(claims, null, 2)}
        </pre>
      </details>
    </div>
  );
}
