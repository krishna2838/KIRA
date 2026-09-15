import type { VideoHit } from "../types";

function youtubeEmbed(url: string): string | null {
  try {
    const u = new URL(url);
    if (u.hostname.endsWith("youtube.com") && u.searchParams.get("v")) {
      return `https://www.youtube.com/embed/${u.searchParams.get("v")}`;
    }
    if (u.hostname === "youtu.be") {
      return `https://www.youtube.com/embed${u.pathname}`;
    }
  } catch {
    /* no-op */
  }
  return null;
}

export function VideoCard({ video }: { video: VideoHit }) {
  const embed = youtubeEmbed(video.url);
  return (
    <a
      href={video.url}
      target="_blank"
      rel="noreferrer"
      className="block rounded-xl overflow-hidden border border-kira-border bg-kira-panel hover:border-kira-accent transition"
    >
      <div className="relative aspect-video bg-kira-bg">
        {video.thumbnail ? (
          <img
            src={video.thumbnail}
            alt={video.title}
            className="w-full h-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-kira-muted">
            ▶
          </div>
        )}
        {video.duration && (
          <span className="absolute bottom-1.5 right-1.5 text-[10px] font-mono bg-black/70 text-white px-1.5 py-0.5 rounded">
            {video.duration}
          </span>
        )}
      </div>
      <div className="p-2">
        <div className="text-xs line-clamp-2 leading-snug">{video.title}</div>
        {video.source && (
          <div className="text-[10px] text-kira-muted mt-1 truncate">
            {video.source}
          </div>
        )}
        {embed && (
          <div className="text-[10px] text-kira-accent mt-1">YouTube ▸</div>
        )}
      </div>
    </a>
  );
}

export function VideoGrid({ videos }: { videos: VideoHit[] }) {
  if (!videos.length) return null;
  return (
    <div className="mt-3 grid grid-cols-2 sm:grid-cols-3 gap-2">
      {videos.slice(0, 6).map((v, i) => (
        <VideoCard key={v.url + i} video={v} />
      ))}
    </div>
  );
}
