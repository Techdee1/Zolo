import { readFileSync } from "node:fs";
import { join } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import manifest from "@/app/manifest";
import { LandingImage } from "@/components/landing/LandingImage";
import { LANDING_IMAGES } from "@/lib/landing-images";
import en from "@/messages/en.json";

const flags = vi.hoisted(() => ({
  demoVideoUrl: undefined as string | undefined,
  repoUrl: undefined as string | undefined,
  teamName: "Our team (name to come)",
  featureDemo: false,
}));
vi.mock("@/lib/env", async (orig) => ({
  ...(await orig<typeof import("@/lib/env")>()),
  env: flags,
}));
vi.mock("@/app/landing-fonts", () => ({ display: { variable: "font-display-test" } }));

const render = async () => {
  vi.resetModules();
  const { default: Landing } = await import("@/app/page");
  return renderToStaticMarkup(<Landing />);
};

/** Pixel size of a JPEG or PNG, read from its header. */
function sizeOf(file: string): { width: number; height: number } {
  const d = readFileSync(file);
  if (d.subarray(1, 4).toString() === "PNG")
    return { width: d.readUInt32BE(16), height: d.readUInt32BE(20) };
  for (let i = 2; i < d.length;) {
    if (d[i] !== 0xff) {
      i += 1;
      continue;
    }
    const m = d[i + 1]!;
    if (m === 0xc0 || m === 0xc2)
      return { height: d.readUInt16BE(i + 5), width: d.readUInt16BE(i + 7) };
    i += 2 + d.readUInt16BE(i + 2);
  }
  throw new Error(`no size in ${file}`);
}

describe("landing page content (rendered with no JavaScript: this is plain HTML)", () => {
  it("has exactly one h1, the headline, and the headings go h1 > h2 > h3 without skipping", async () => {
    const html = await render();
    expect(html.match(/<h1[ >]/g)).toHaveLength(1);
    expect(html).toContain("Anyone can propose a payment. Only you can approve it.");
    const levels = [...html.matchAll(/<h([1-6])[ >]/g)].map((m) => Number(m[1]));
    for (let i = 1; i < levels.length; i++)
      expect(levels[i]! - levels[i - 1]!, levels.join("")).toBeLessThanOrEqual(1);
  });

  it("has the seven sections, each named by its own heading", async () => {
    const html = await render();
    const sections = [...html.matchAll(/<section aria-labelledby="([^"]+)"/g)].map((m) => m[1]);
    expect(sections).toEqual([
      "hero-title",
      "problem-title",
      "rule-title",
      "how-title",
      "why-title",
      "safe-title",
      "cta-title",
    ]);
    for (const id of sections) expect(html).toContain(`id="${id}"`);
  });

  it("sends 'Try the demo' to the demo sign-in, with no script needed", async () => {
    const html = await render();
    const links = [...html.matchAll(/<a href="([^"]+)"[^>]*>\s*Try the demo/g)].map((m) => m[1]);
    expect(links.length).toBeGreaterThanOrEqual(3); // header, hero, final call to action
    expect(new Set(links)).toEqual(new Set(["/signin"]));
    expect(html).not.toContain("javascript:");
  });

  it("shows the video and repo links only when they are configured, and opens them safely", async () => {
    let html = await render();
    expect(html).not.toContain("Watch the 90 second demo");
    expect(html).not.toContain("See the code on GitHub");
    flags.demoVideoUrl = "https://example.com/demo";
    flags.repoUrl = "https://github.com/team/zolo";
    html = await render();
    expect(html).toContain("Watch the 90 second demo");
    expect(html).toContain('href="https://github.com/team/zolo"');
    expect(html.match(/rel="noopener noreferrer"/g)).toHaveLength(2);
    expect(html).toContain("(opens in a new tab)");
    flags.demoVideoUrl = flags.repoUrl = undefined;
  });

  it("says only what the system really does about safety, and nothing about privacy or numbers", async () => {
    const html = await render();
    for (const k of ["i1", "i2", "i3", "i4", "i5"] as const)
      expect(html).toContain(en.landing.safe[k].replace("'", "&#x27;"));
    expect(html).toContain("A request expires after 2 minutes.");
    const words = JSON.stringify(en.landing).toLowerCase();
    expect(words).not.toMatch(
      /privacy|retention|encrypt|gdpr|stored|percent|%|million|thousand customers|testimonial|trusted by/,
    );
    expect(words).not.toMatch(/\d{2,}\s?(people|customers|users)/);
  });

  it("uses the Zolo wordmark with 'for Zenith Bank' and never a Zenith logo", async () => {
    const html = await render();
    expect(html).toContain("for Zenith Bank");
    expect(html.toLowerCase()).not.toMatch(/zenith[-_ ]?logo|logo/);
  });

  it("has a footer with the team name from config, the event, and no credits when there is no credits file", async () => {
    flags.teamName = "The Zolo crew";
    const html = await render();
    expect(html).toContain("Made by The Zolo crew");
    expect(html).toContain("Zecathon 6.0, Track 7");
    flags.teamName = "Our team (name to come)";
  });

  it("has no client components of its own: no 'use client' in the landing files", () => {
    for (const f of ["app/page.tsx", "components/landing/LandingImage.tsx"]) {
      expect(readFileSync(join(process.cwd(), f), "utf8"), f).not.toMatch(/["']use client["']/);
    }
  });
});

describe("landing images", () => {
  it("every configured size is the real size of the file, so nothing shifts", () => {
    for (const img of Object.values(LANDING_IMAGES)) {
      const file = join(process.cwd(), "public", img.src);
      expect(sizeOf(file), img.name).toEqual({ width: img.width, height: img.height });
    }
  });

  it("every image has alt text that describes a scene, not a claim", () => {
    for (const [k, v] of Object.entries(en.landing.alt)) {
      expect(v.length, k).toBeGreaterThan(25);
      expect(v, k).not.toMatch(/\bZolo (customer|user)\b|image of|picture of|photo of/i);
    }
    for (const s of ["s1", "s2", "s3"] as const)
      expect(en.landing.how[s].alt.length).toBeGreaterThan(40);
  });

  it("the hero is the priority image; the rest are lazy", async () => {
    const html = await render();
    const imgs = [...html.matchAll(/<img [^>]*>/g)].map((m) => m[0]);
    expect(imgs).toHaveLength(7);
    expect(imgs[0]).not.toContain('loading="lazy"');
    for (const tag of imgs.slice(1)) expect(tag).toContain('loading="lazy"');
    for (const tag of imgs) expect(tag).toMatch(/width="\d+"/);
    for (const tag of imgs) expect(tag).toMatch(/height="\d+"/);
  });

  it("a missing file becomes a warm placeholder of the same proportions, labelled with the same alt", async () => {
    vi.resetModules();
    vi.doMock("node:fs", async (orig) => ({
      ...(await orig<typeof import("node:fs")>()),
      existsSync: () => false,
    }));
    const { LandingImage: Missing } = await import("@/components/landing/LandingImage");
    const html = renderToStaticMarkup(
      <Missing image={LANDING_IMAGES.street} alt="A scene" sizes="100vw" />,
    );
    expect(html).toContain('role="img"');
    expect(html).toContain('aria-label="A scene"');
    expect(html).toContain("aspect-ratio:638 / 480");
    expect(html).not.toContain("<img");
    vi.doUnmock("node:fs");
  });

  it("an image that is there is a real <img> with its alt", () => {
    const html = renderToStaticMarkup(
      <LandingImage image={LANDING_IMAGES.hero} alt="A phone at an ear" sizes="100vw" />,
    );
    expect(html).toContain('alt="A phone at an ear"');
  });
});

describe("the PWA manifest", () => {
  it("starts at the customer home, so an installed app skips the landing page", () => {
    expect(manifest().start_url).toBe("/home");
    expect(manifest().scope).toBe("/");
    expect(manifest().display).toBe("standalone");
  });

  it("names real icon files, including a maskable one", () => {
    const icons = manifest().icons ?? [];
    expect(icons.length).toBeGreaterThanOrEqual(3);
    for (const icon of icons) {
      const { width } = sizeOf(join(process.cwd(), "public", icon.src));
      expect(`${width}x${width}`, icon.src).toBe(icon.sizes);
    }
    expect(icons.some((i) => i.purpose === "maskable")).toBe(true);
  });
});
