import { useCallback, useEffect, useState } from "react";

import { getNotifications, markNotificationsRead } from "../api";
import type { AppNotification, User } from "../api";
import Feed from "./Feed";
import Notifications from "./Notifications";

export default function MainArea({ user }: { user: User }) {
  const [tab, setTab] = useState<"feed" | "notifications">("feed");
  const [items, setItems] = useState<AppNotification[] | null>(null);
  const [unread, setUnread] = useState(0);

  const load = useCallback(async () => {
    try {
      const data = await getNotifications();
      setItems(data.notifications);
      setUnread(data.unread);
    } catch {
      // Notifications are optional: if notification-service is down the feed still works.
    }
  }, []);

  // Check for new notifications every 5 seconds, so the badge updates on every tab.
  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 5000);
    return () => clearInterval(timer);
  }, [load]);

  async function markRead() {
    try {
      const result = await markNotificationsRead();
      setUnread(result.unread);
      await load();
    } catch {
      // ignore: the next refresh will show the real state
    }
  }

  const tabClass = (active: boolean) =>
    `flex-1 rounded-lg py-2 text-sm font-semibold transition ${
      active ? "bg-brand text-white shadow" : "opacity-70 hover:opacity-100"
    }`;

  return (
    <div className="space-y-4">
      <div className="flex gap-1 rounded-xl bg-black/5 p-1 dark:bg-white/10">
        <button className={tabClass(tab === "feed")} onClick={() => setTab("feed")}>
          Feed
        </button>
        <button className={tabClass(tab === "notifications")} onClick={() => setTab("notifications")}>
          Notifications
          {unread > 0 && (
            <span className="ml-2 rounded-full bg-accent px-2 py-0.5 text-xs font-bold text-white">{unread}</span>
          )}
        </button>
      </div>

      {tab === "feed" ? (
        <Feed user={user} />
      ) : (
        <Notifications items={items} unread={unread} onMarkRead={() => void markRead()} />
      )}
    </div>
  );
}
