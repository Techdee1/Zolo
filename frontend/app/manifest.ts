import type { MetadataRoute } from "next";

/**
 * The installed app opens on the customer home, not the landing page: someone who added Zolo to
 * their home screen wants to pay, not to be told what Zolo is.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Zolo for Zenith Bank",
    short_name: "Zolo",
    description: "Hear a payment before you approve it.",
    start_url: "/home",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#f5f5f7",
    theme_color: "#f5f5f7",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
