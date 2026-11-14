import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";

import { createTweet, deleteTweet, getLikes, likeTweet, listTweets, unlikeTweet } from "../api";
import type { LikeInfo, Tweet, User } from "../api";

function timeAgo(iso: string): string {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong";
}

export default function Feed({ user }: { user: User }) {
  const [tweets, setTweets] = useState<Tweet[] | null>(null);
  const [likes, setLikes] = useState<Record<string, LikeInfo>>({});
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const list = await listTweets();
      setTweets(list);
      setLoadError("");
      if (list.length > 0) {
        try {
          setLikes(await getLikes(list.map((t) => t.id)));
        } catch {
          // Likes are optional: if like-service is down the tweets still show.
        }
      }
    } catch (err) {
      setLoadError(messageOf(err));
    }
  }, []);

  // Load now, then refresh every 5 seconds so tweets and likes from other accounts show up.
  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 5000);
    return () => clearInterval(timer);
  }, [load]);

  async function post(event: FormEvent) {
    event.preventDefault();
    if (!text.trim()) return;
    setError("");
    setBusy(true);
    try {
      await createTweet(text.trim());
      setText("");
      await load();
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    setError("");
    try {
      await deleteTweet(id);
      await load();
    } catch (err) {
      setError(messageOf(err));
    }
  }

  async function toggleLike(tweet: Tweet) {
    setError("");
    const liked = likes[String(tweet.id)]?.liked_by_me === true;
    try {
      const result = liked ? await unlikeTweet(tweet.id) : await likeTweet(tweet.id);
      setLikes((old) => ({
        ...old,
        [String(tweet.id)]: { count: result.count, liked_by_me: result.liked },
      }));
    } catch (err) {
      setError(messageOf(err));
    }
  }

  const left = 280 - text.length;

  return (
    <div className="space-y-4">
      <form
        onSubmit={post}
        className="rounded-2xl border border-black/5 bg-card p-5 shadow-sm dark:border-white/10 dark:bg-card-dark"
      >
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={280}
          rows={3}
          placeholder="What's happening?"
          className="w-full resize-none rounded-xl border border-black/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/30 dark:border-white/10 dark:bg-surface-dark"
        />
        <div className="mt-3 flex items-center justify-between">
          <span className={`text-xs ${left < 20 ? "text-accent" : "opacity-60"}`}>{left} left</span>
          <button
            type="submit"
            disabled={busy || !text.trim()}
            className="rounded-full bg-brand px-5 py-2 text-sm font-semibold text-white transition hover:bg-brand-dark disabled:opacity-50"
          >
            {busy ? "Posting..." : "Post"}
          </button>
        </div>
      </form>

      {error && (
        <div className="rounded-xl bg-red-100 px-4 py-2 text-sm text-red-700 dark:bg-red-900/40 dark:text-red-300">
          {error}
        </div>
      )}

      {loadError && (
        <div className="rounded-xl bg-amber-100 px-4 py-2 text-sm text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
          Could not load tweets: {loadError}
        </div>
      )}

      {tweets === null && !loadError && (
        <div className="space-y-3">
          <div className="h-24 animate-pulse rounded-2xl bg-black/5 dark:bg-white/10" />
          <div className="h-24 animate-pulse rounded-2xl bg-black/5 dark:bg-white/10" />
        </div>
      )}

      {tweets !== null && tweets.length === 0 && (
        <div className="rounded-2xl border border-dashed border-black/10 p-8 text-center text-sm opacity-70 dark:border-white/20">
          No tweets yet. Be the first to post.
        </div>
      )}

      {tweets?.map((tweet) => {
        const info = likes[String(tweet.id)];
        const liked = info?.liked_by_me === true;
        return (
          <article
            key={tweet.id}
            className="rounded-2xl border border-black/5 bg-card p-5 shadow-sm dark:border-white/10 dark:bg-card-dark"
          >
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand to-accent font-bold uppercase text-white">
                {tweet.username.charAt(0)}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate text-sm">
                    <span className="font-bold">@{tweet.username}</span>
                    <span className="ml-2 opacity-60">{timeAgo(tweet.created_at)}</span>
                  </p>
                  {tweet.user_id === user.id && (
                    <button
                      onClick={() => void remove(tweet.id)}
                      className="rounded-full px-3 py-1 text-xs font-semibold text-red-500 transition hover:bg-red-500/10"
                    >
                      Delete
                    </button>
                  )}
                </div>
                <p className="mt-1 whitespace-pre-wrap break-words text-sm">{tweet.content}</p>
                <button
                  onClick={() => void toggleLike(tweet)}
                  aria-label={liked ? "Unlike this tweet" : "Like this tweet"}
                  className={`mt-3 flex items-center gap-1.5 rounded-full px-3 py-1 text-sm transition hover:bg-accent/10 ${
                    liked ? "font-semibold text-accent" : "opacity-70"
                  }`}
                >
                  <span>{liked ? "♥" : "♡"}</span>
                  <span>{info?.count ?? 0}</span>
                </button>
              </div>
            </div>
          </article>
        );
      })}
    </div>
  );
}
