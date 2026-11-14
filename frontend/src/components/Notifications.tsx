import type { AppNotification } from "../api";
import { timeAgo } from "../time";

interface Props {
  items: AppNotification[] | null;
  unread: number;
  onMarkRead: () => void;
}

export default function Notifications({ items, unread, onMarkRead }: Props) {
  if (items === null) {
    return (
      <div className="space-y-3">
        <div className="h-16 animate-pulse rounded-2xl bg-black/5 dark:bg-white/10" />
        <div className="h-16 animate-pulse rounded-2xl bg-black/5 dark:bg-white/10" />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm opacity-70">{unread > 0 ? `${unread} unread` : "You are all caught up"}</p>
        {unread > 0 && (
          <button
            onClick={onMarkRead}
            className="rounded-full border border-black/10 px-4 py-1.5 text-xs font-semibold transition hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10"
          >
            Mark all as read
          </button>
        )}
      </div>

      {items.length === 0 && (
        <div className="rounded-2xl border border-dashed border-black/10 p-8 text-center text-sm opacity-70 dark:border-white/20">
          No notifications yet. When someone likes your tweet, you will see it here.
        </div>
      )}

      {items.map((item) => (
        <div
          key={item.id}
          className={`flex items-start gap-3 rounded-2xl border p-4 shadow-sm ${
            item.is_read
              ? "border-black/5 bg-card dark:border-white/10 dark:bg-card-dark"
              : "border-brand/40 bg-brand/5 dark:bg-brand/10"
          }`}
        >
          <span className="text-xl">{item.type === "like" ? "♥" : "🎉"}</span>
          <div className="min-w-0 flex-1">
            <p className="break-words text-sm">{item.message}</p>
            <p className="mt-0.5 text-xs opacity-60">{timeAgo(item.created_at)}</p>
          </div>
          {!item.is_read && <span className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full bg-brand" />}
        </div>
      ))}
    </div>
  );
}
