export default function Logo() {
  return (
    <div className="flex items-center gap-2">
      <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand to-accent text-lg text-white shadow-md">
        ⚡
      </div>
      <span className="font-heading text-xl font-extrabold tracking-tight">MiniTweet</span>
    </div>
  );
}
