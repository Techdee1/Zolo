import { existsSync } from "node:fs";
import { join } from "node:path";
import Image from "next/image";
import type { LandingImage as Img } from "@/lib/landing-images";

/**
 * A landing photo. With next/image it is served as AVIF or WebP at the right size, with its real
 * width and height so nothing jumps. If the file is not there yet, a warm gradient of the same
 * proportions stands in (and development logs which one is missing), so the page always works.
 */
export function LandingImage({
  image,
  alt,
  priority = false,
  sizes,
}: {
  image: Img;
  alt: string;
  priority?: boolean;
  sizes: string;
}) {
  const present = existsSync(join(process.cwd(), "public", image.src));
  if (!present) {
    if (process.env.NODE_ENV === "development") {
      console.warn(`[landing] missing image: public${image.src}`);
    }
    return (
      <div
        role="img"
        aria-label={alt}
        className="land-placeholder"
        style={{ aspectRatio: `${image.width} / ${image.height}` }}
      />
    );
  }
  return (
    <Image
      src={image.src}
      alt={alt}
      width={image.width}
      height={image.height}
      sizes={sizes}
      priority={priority}
      loading={priority ? undefined : "lazy"}
    />
  );
}
