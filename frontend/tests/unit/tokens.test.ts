import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { FADE_SECONDS, PRESS_SCALE, SPRING, toSpring } from "@/lib/motion";
import { contrast } from "./contrast";

const css = readFileSync(join(process.cwd(), "styles", "tokens.css"), "utf8");

/** The text between the braces that open at `open` (matching nested braces). */
function block(from: number): string {
  const open = css.indexOf("{", from);
  let depth = 0;
  for (let i = open; i < css.length; i++) {
    if (css[i] === "{") depth++;
    if (css[i] === "}" && --depth === 0) return css.slice(open + 1, i);
  }
  throw new Error("unbalanced braces in tokens.css");
}

function declarations(body: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const m of body.replace(/\/\*[\s\S]*?\*\//g, "").matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
    out[m[1]!] = m[2]!.trim().replace(/\s+/g, " ");
  }
  return out;
}

const mediaRoot = (query: string): Record<string, string> => {
  const at = css.indexOf(`@media ${query}`);
  if (at < 0) throw new Error(`no @media ${query} in tokens.css`);
  return declarations(block(css.indexOf(":root", at)));
};

const light = declarations(block(css.indexOf(":root")));
const dark = { ...light, ...mediaRoot("(prefers-color-scheme: dark)") };
const themes = { light, dark } as const;
const hex = (v: string | undefined) => (v ?? "").toLowerCase();

// ── The PRD's colour table, value for value ──────────────────────────────────────────────────
const COLOURS: Record<string, [string, string]> = {
  "--color-brand": ["#D7191E", "#D7191E"],
  "--color-brand-pressed": ["#B3141A", "#B3141A"],
  "--color-brand-text": ["#D7191E", "#FF5A5F"],
  "--color-graphite": ["#3A3A3C", "#3A3A3C"],
  "--color-bg": ["#FFFFFF", "#000000"],
  "--color-bg-backdrop": ["#E9E9EE", "#000000"],
  "--color-bg-grouped": ["#F5F5F7", "#111113"],
  "--color-bg-elevated": ["#FFFFFF", "#1C1C1E"],
  "--color-text": ["#1C1C1E", "#F5F5F7"],
  "--color-text-secondary": ["#6E6E73", "#A1A1A6"],
  "--color-success": ["#137333", "#32D74B"],
  "--color-warning": ["#A15C00", "#FFB340"],
  "--color-critical": ["#B3141A", "#FF5A5F"],
  "--color-focus": ["#1C1C1E", "#FFFFFF"],
};

describe("colour tokens match the PRD exactly", () => {
  for (const [name, [l, d]] of Object.entries(COLOURS)) {
    it(`${name}: ${l} light, ${d} dark`, () => {
      expect(hex(light[name])).toBe(l.toLowerCase());
      expect(hex(dark[name])).toBe(d.toLowerCase());
    });
  }

  it("hairlines are translucent: rgba(60,60,67,0.18) light, rgba(84,84,88,0.6) dark", () => {
    expect(light["--color-separator"]).toBe("rgb(60 60 67 / 0.18)");
    expect(dark["--color-separator"]).toBe("rgb(84 84 88 / 0.6)");
  });
});

// ── Contrast: every pair the screens can produce, in both themes ─────────────────────────────
describe.each(["light", "dark"] as const)("contrast in %s mode", (theme) => {
  const t = themes[theme];
  const surfaces = ["--color-bg", "--color-bg-grouped", "--color-bg-elevated"] as const;

  it.each([
    "--color-text",
    "--color-text-secondary",
    "--color-brand-text",
    "--color-success",
    "--color-warning",
    "--color-critical",
  ])("%s is at least 4.5:1 on every surface", (fg) => {
    for (const bg of surfaces) {
      expect(contrast(t[fg]!, t[bg]!), `${fg} on ${bg}`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("white text on the brand fill, its pressed state and graphite is at least 4.5:1", () => {
    for (const fill of ["--color-brand", "--color-brand-pressed", "--color-graphite"]) {
      expect(contrast(t["--color-on-brand"]!, t[fill]!), fill).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("the focus ring is at least 3:1 on every surface", () => {
    for (const bg of surfaces) {
      expect(contrast(t["--color-focus"]!, t[bg]!), bg).toBeGreaterThanOrEqual(3);
    }
  });

  it("the brand fill is at least 3:1 against the page, so the button's edge is visible", () => {
    expect(contrast(t["--color-brand"]!, t["--color-bg"]!)).toBeGreaterThanOrEqual(3);
  });
});

// ── The hero: the always-dark band. Its text is checked on every surface it can sit on, including
// the spot where the red glow is strongest (the glow blended over the band at its full alpha). ──
const blend = (rgba: string, under: string): string => {
  const [r, g, b, a] = rgba.match(/[\d.]+/g)!.map(Number) as [number, number, number, number];
  const base = [1, 3, 5].map((i) => parseInt(under.slice(i, i + 2), 16));
  return `#${[r, g, b]
    .map((c, i) => Math.round(c * a + base[i]! * (1 - a)))
    .map((c) => c.toString(16).padStart(2, "0"))
    .join("")}`;
};

describe.each(["light", "dark"] as const)("the hero band in %s mode", (theme) => {
  const t = themes[theme];
  const surfaces = {
    "--hero-bg": t["--hero-bg"]!,
    "--hero-bg-end": t["--hero-bg-end"]!,
    "--hero-surface": t["--hero-surface"]!,
    "the red glow": blend(t["--hero-glow"]!, t["--hero-bg"]!),
  };

  it.each([
    "--hero-text",
    "--hero-text-secondary",
    "--hero-accent-text",
    "--hero-success",
    "--hero-warning",
  ])("%s is at least 4.5:1 on every hero surface", (fg) => {
    for (const [name, bg] of Object.entries(surfaces)) {
      expect(contrast(t[fg]!, bg), `${fg} on ${name}`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("the white focus ring is at least 3:1 on every hero surface", () => {
    for (const bg of Object.values(surfaces))
      expect(contrast("#ffffff", bg)).toBeGreaterThanOrEqual(3);
  });

  it("the hero reads as a band on the page: at least 1.1:1 against the page behind it", () => {
    expect(contrast(t["--hero-bg"]!, t["--color-bg-grouped"]!)).toBeGreaterThanOrEqual(1.1);
  });
});

describe("a limit worth knowing", () => {
  it("graphite on a black page is under 3:1, so a graphite chip in dark mode needs a border", () => {
    // Not a failure: the chip's text is 11:1 on graphite. But the SHAPE is not identifiable from
    // the fill alone, so components that use graphite must also draw a separator border.
    expect(contrast(dark["--color-graphite"]!, dark["--color-bg"]!)).toBeLessThan(3);
  });
});

// ── Type, spacing, shape ──────────────────────────────────────────────────────────────────────
const TYPE: Record<string, [string, string, string, string]> = {
  hero: ["4.5rem", "700", "1", "-0.035em"],
  display: ["2.125rem", "700", "1.08", "-0.025em"],
  amount: ["3.5rem", "700", "1.05", "-0.02em"],
  code: ["3rem", "600", "1.1", "0.08em"],
  title: ["1.75rem", "600", "1.15", "-0.01em"],
  headline: ["1.25rem", "600", "1.25", "0"],
  body: ["1.0625rem", "400", "1.47", "0"],
  secondary: ["0.9375rem", "400", "1.4", "0"],
  caption: ["0.8125rem", "500", "1.35", "0.01em"],
};

describe("type scale matches the PRD", () => {
  for (const [name, [size, weight, leading, tracking]] of Object.entries(TYPE)) {
    it(`${name}: ${size} / ${weight} / ${leading} / ${tracking}`, () => {
      expect(light[`--type-${name}-size`]).toBe(size);
      expect(light[`--type-${name}-weight`]).toBe(weight);
      expect(light[`--type-${name}-leading`]).toBe(leading);
      expect(light[`--type-${name}-tracking`]).toBe(tracking);
    });
  }

  it("every size is in rem, so the user's text-size setting scales it", () => {
    for (const [k, v] of Object.entries(light))
      if (k.endsWith("-size")) expect(v, k).toMatch(/rem$/);
  });

  it("nothing is smaller than the caption (0.8125rem = 13px)", () => {
    const sizes = Object.entries(light)
      .filter(([k]) => k.startsWith("--type-") && k.endsWith("-size"))
      .map(([, v]) => parseFloat(v));
    expect(Math.min(...sizes)).toBe(0.8125);
  });

  it("large type tightens its tracking and small type loosens it, never one value for all", () => {
    expect(parseFloat(light["--type-amount-tracking"]!)).toBeLessThan(0);
    expect(parseFloat(light["--type-caption-tracking"]!)).toBeGreaterThan(0);
  });

  it("the bigger the type, the tighter the tracking (hero < display < title < body)", () => {
    const track = (n: string) => parseFloat(light[`--type-${n}-tracking`]!);
    expect(track("hero")).toBeLessThan(track("display"));
    expect(track("display")).toBeLessThan(track("title"));
    expect(track("title")).toBeLessThanOrEqual(track("body"));
  });

  it("the biggest type has the tightest leading", () => {
    const lead = (n: string) => parseFloat(light[`--type-${n}-leading`]!);
    expect(lead("hero")).toBeLessThan(lead("title"));
    expect(lead("title")).toBeLessThan(lead("body"));
  });

  it("uses system fonts only: no web font is named or loaded", () => {
    expect(light["--font-sans"]).toBe(
      '-apple-system, BlinkMacSystemFont, "SF Pro Text", Roboto, "Segoe UI", sans-serif',
    );
    expect(css).not.toMatch(/@font-face|fonts\.googleapis|@import url/i);
  });
});

describe("spacing, targets and shape", () => {
  it("spacing steps are 4, 8, 12, 16, 24, 32, 48, 64 px", () => {
    const px = ["1", "2", "3", "4", "6", "8", "12", "16"].map(
      (n) => parseFloat(light[`--space-${n}`]!) * 16,
    );
    expect(px).toEqual([4, 8, 12, 16, 24, 32, 48, 64]);
  });

  it("screen side padding is 1.25rem, the column is 30rem", () => {
    expect(light["--space-screen-x"]).toBe("1.25rem");
    expect(light["--layout-max"]).toBe("30rem");
  });

  it("targets: 48px minimum, primary buttons 3.5rem, 8px between them", () => {
    expect(parseFloat(light["--target-min"]!) * 16).toBe(48);
    expect(light["--target-primary"]).toBe("3.5rem");
    expect(parseFloat(light["--target-gap"]!) * 16).toBe(8);
  });

  it("radius: 12px controls, 20px cards, 28px sheets", () => {
    expect([light["--radius-control"], light["--radius-card"], light["--radius-sheet"]]).toEqual([
      "12px",
      "20px",
      "28px",
    ]);
  });

  it("the focus ring is 3px with a 2px offset", () => {
    expect([light["--focus-width"], light["--focus-offset"]]).toEqual(["3px", "2px"]);
  });
});

// ── Materials and the user's accessibility settings ──────────────────────────────────────────
describe("materials and accessibility preferences", () => {
  it("chrome is translucent by default: 72% over a 20px blur with saturation", () => {
    expect(light["--material-opacity"]).toBe("0.72");
    expect(light["--material-bg"]).toContain("72%");
    expect(light["--material-filter"]).toBe("blur(20px) saturate(180%)");
  });

  it("reduced transparency makes chrome solid and removes the blur", () => {
    const m = mediaRoot("(prefers-reduced-transparency: reduce)");
    expect(m["--material-bg"]).toBe("var(--color-bg)");
    expect(m["--material-filter"]).toBe("none");
  });

  it("more contrast: solid chrome, opaque hairlines, strong secondary text, thicker focus ring", () => {
    const m = mediaRoot("(prefers-contrast: more)");
    expect(m["--material-bg"]).toBe("var(--color-bg)");
    expect(m["--material-filter"]).toBe("none");
    expect(m["--color-separator"]).toMatch(/^#/); // opaque, not rgb(... / alpha)
    expect(m["--color-text-secondary"]).toBe("var(--color-text)");
    expect(m["--focus-width"]).toBe("4px");
    expect(parseFloat(m["--border-width"]!)).toBeGreaterThanOrEqual(2);
  });

  it("reduced motion removes the press scale", () => {
    expect(light["--motion-press-scale"]).toBe("0.97");
    expect(mediaRoot("(prefers-reduced-motion: reduce)")["--motion-press-scale"]).toBe("1");
  });
});

// ── Motion: CSS and TypeScript must agree ────────────────────────────────────────────────────
describe("motion tokens", () => {
  it("lib/motion.ts mirrors the springs in tokens.css", () => {
    expect(SPRING.default).toEqual({
      damping: Number(light["--motion-spring-damping"]),
      response: Number(light["--motion-spring-response"]),
    });
    expect(SPRING.sheet).toEqual({
      damping: Number(light["--motion-sheet-damping"]),
      response: Number(light["--motion-sheet-response"]),
    });
    expect(PRESS_SCALE).toBe(Number(light["--motion-press-scale"]));
    expect(FADE_SECONDS * 1000).toBe(parseFloat(light["--motion-fade-duration"]!));
  });

  it("the defaults are the skill's: critically damped 0.4s, sheets 0.8 damping and 0.3s", () => {
    expect(SPRING.default).toEqual({ damping: 1, response: 0.4 });
    expect(SPRING.sheet).toEqual({ damping: 0.8, response: 0.3 });
  });

  it("a damping ratio of 1 converts to a CRITICALLY damped spring (no overshoot)", () => {
    const s = toSpring(SPRING.default);
    expect(s.damping ** 2).toBeCloseTo(4 * s.stiffness * s.mass, 6); // c² = 4km
  });

  it("a ratio below 1 is under-damped (it bounces), and faster response is stiffer", () => {
    const sheet = toSpring(SPRING.sheet);
    expect(sheet.damping ** 2).toBeLessThan(4 * sheet.stiffness * sheet.mass);
    expect(sheet.stiffness).toBeGreaterThan(toSpring(SPRING.default).stiffness);
  });
});

describe("the agent tint stays readable", () => {
  it("text and secondary text keep 4.5:1 on the tinted agent background, in both themes", () => {
    for (const [name, t] of Object.entries(themes)) {
      for (const fg of ["--color-text", "--color-text-secondary"] as const)
        expect(contrast(t[fg]!, t["--tint-agent"]!), `${name} ${fg}`).toBeGreaterThanOrEqual(4.5);
    }
  });
  it("the tint is subtle: nearly as light as the grouped background, only a little cooler", () => {
    for (const t of Object.values(themes)) {
      const ratio = contrast(t["--tint-agent"]!, t["--color-bg-grouped"]!);
      expect(ratio).toBeLessThan(1.1);
      expect(hex(t["--tint-agent"])).not.toBe(hex(t["--color-bg-grouped"]));
    }
  });
});

describe("press feedback and release", () => {
  it("scales to 0.97 on press and settles with a spring on release; none of it under reduced motion", () => {
    expect(light["--motion-press-scale"]).toBe("0.97");
    expect(light["--motion-release-duration"]).toBe("420ms");
    expect(light["--motion-spring-ease"]).toMatch(/^linear\(/);
    const reduced = mediaRoot("(prefers-reduced-motion: reduce)");
    expect(reduced["--motion-press-scale"]).toBe("1");
    expect(reduced["--motion-release-duration"]).toBe("0ms");
  });
});

describe("the landing page palette", () => {
  const land = ["--land-bg", "--land-surface"] as const;
  it("ink and secondary text keep 4.5:1 on the warm page and on cards, in both themes", () => {
    for (const [name, t] of Object.entries(themes))
      for (const fg of ["--land-ink", "--land-ink-secondary", "--land-accent-text"] as const)
        for (const bg of land)
          expect(contrast(t[fg]!, t[bg]!), `${name} ${fg} on ${bg}`).toBeGreaterThanOrEqual(4.5);
  });
  it("white text on the red button keeps 4.5:1", () => {
    expect(contrast(light["--color-on-brand"]!, light["--color-brand"]!)).toBeGreaterThanOrEqual(
      4.5,
    );
  });
  it("the grain is faint, and gone under reduced transparency and more contrast", () => {
    expect(parseFloat(light["--land-grain-opacity"]!)).toBeLessThanOrEqual(0.08);
    expect(mediaRoot("(prefers-reduced-transparency: reduce)")["--land-grain-opacity"]).toBe("0");
    expect(mediaRoot("(prefers-contrast: more)")["--land-grain-opacity"]).toBe("0");
    expect(mediaRoot("(prefers-reduced-transparency: reduce)")["--land-material-filter"]).toBe(
      "none",
    );
  });
});
