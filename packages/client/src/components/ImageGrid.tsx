import { useState } from "react";
import type { ImageHit } from "../types";

export function ImageGrid({ images }: { images: ImageHit[] }) {
  const [zoom, setZoom] = useState<ImageHit | null>(null);
  if (!images.length) return null;

  return (
    <>
      <div className="mt-3 grid grid-cols-3 sm:grid-cols-4 gap-1.5">
        {images.slice(0, 12).map((img, i) => (
          <button
            key={img.url + i}
            onClick={() => setZoom(img)}
            className="relative aspect-square rounded-lg overflow-hidden border border-kira-border bg-kira-bg hover:border-kira-accent"
            title={img.alt || img.source}
          >
            <img
              src={img.thumbnail || img.url}
              alt={img.alt || ""}
              loading="lazy"
              className="w-full h-full object-cover"
              onError={(e) =>
                ((e.currentTarget as HTMLImageElement).style.display = "none")
              }
            />
          </button>
        ))}
      </div>

      {zoom && (
        <div
          className="fixed inset-0 bg-black/85 z-50 flex flex-col items-center justify-center p-6"
          onClick={() => setZoom(null)}
        >
          <img
            src={zoom.url}
            alt={zoom.alt || ""}
            className="max-w-full max-h-[80vh] rounded"
            onClick={(e) => e.stopPropagation()}
          />
          <div className="mt-3 text-xs text-kira-muted text-center max-w-xl">
            {zoom.alt && <div>{zoom.alt}</div>}
            {zoom.source && (
              <a
                href={zoom.source}
                target="_blank"
                rel="noreferrer"
                className="text-kira-accent underline"
                onClick={(e) => e.stopPropagation()}
              >
                {zoom.source}
              </a>
            )}
          </div>
        </div>
      )}
    </>
  );
}
