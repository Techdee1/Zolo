import { BadgeCheck } from "lucide-react";
import type { Metadata } from "next";
import { LandingImage } from "@/components/landing/LandingImage";
import { env } from "@/lib/env";
import { t } from "@/lib/i18n";
import { readImageCredits } from "@/lib/image-credits";
import { LANDING_IMAGES as IMG } from "@/lib/landing-images";
import { display } from "./landing-fonts";

export const metadata: Metadata = {
  title: { absolute: "Zolo: anyone can propose a payment, only you can approve it" },
  description:
    "Zolo lets blind and low-vision customers pay at an agent or a POS by hearing the request first, then approving it with their own passkey.",
};

/**
 * The landing page: what Zolo is, in ten seconds, then the demo. A server component with no client
 * JavaScript of its own, so it reads and links with scripts off. Written to sound like a person.
 */
export default function Landing() {
  const credits = readImageCredits();
  const demoHref = "/signin";

  return (
    <div className={`landing ${display.variable}`} lang="en">
      <header className="land-header">
        <div className="land-wrap">
          <p className="wordmark m-0">
            {t("app.name")} <span className="wordmark-sub">{t("app.forBank")}</span>
          </p>
          <a href={demoHref} className="land-pill press">
            {t("landing.tryDemo")}
          </a>
        </div>
      </header>

      <main id="main">
        {/* 1. Hero */}
        <section aria-labelledby="hero-title" className="land-wrap land-hero">
          <div className="land-hero-copy">
            <h1 id="hero-title" className="land-display">
              {t("landing.hero.title")}
            </h1>
            <p className="land-lede">{t("landing.hero.lede")}</p>
            <div className="land-actions">
              <a href={demoHref} className="land-btn press">
                {t("landing.tryDemo")}
              </a>
              {env.demoVideoUrl ? (
                <a
                  href={env.demoVideoUrl}
                  className="land-link"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {t("landing.watchDemo")}
                  <span className="sr-only"> ({t("landing.newTab")})</span>
                </a>
              ) : null}
            </div>
          </div>
          <figure className="land-photo tilt-a drift">
            <LandingImage
              image={IMG.hero}
              alt={t("landing.alt.hero")}
              priority
              sizes="(min-width: 56rem) 26rem, 100vw"
            />
          </figure>
        </section>

        {/* 2. The problem */}
        <section aria-labelledby="problem-title" className="land-section">
          <div className="land-wrap land-split">
            <div className="reveal grid gap-5">
              <h2 id="problem-title" className="land-display-md">
                {t("landing.problem.title")}
              </h2>
              <p className="land-lede">{t("landing.problem.p1")}</p>
              <p className="land-lede">{t("landing.problem.p2")}</p>
            </div>
            <figure className="land-photo tilt-b reveal">
              <LandingImage
                image={IMG.counter}
                alt={t("landing.alt.counter")}
                sizes="(min-width: 56rem) 30rem, 100vw"
              />
            </figure>
          </div>
        </section>

        {/* 3. The rule */}
        <section aria-labelledby="rule-title" className="land-section">
          <div className="land-wrap reveal grid gap-6">
            <h2 id="rule-title" className="land-rule">
              {t("landing.rule.title")}
            </h2>
            <p className="land-lede">{t("landing.rule.p")}</p>
          </div>
        </section>

        {/* 4. How it works */}
        <section aria-labelledby="how-title" className="land-section">
          <div className="land-wrap">
            <div className="land-split reveal">
              <div className="grid gap-4">
                <h2 id="how-title" className="land-display-md">
                  {t("landing.how.title")}
                </h2>
                <p className="land-lede">{t("landing.how.intro")}</p>
              </div>
              <figure className="land-photo tilt-a">
                <LandingImage
                  image={IMG.hands}
                  alt={t("landing.alt.hands")}
                  sizes="(min-width: 56rem) 30rem, 100vw"
                />
              </figure>
            </div>
            <ol className="land-steps">
              {(
                [
                  ["s1", IMG.shotAgent],
                  ["s2", IMG.shotReview],
                  ["s3", IMG.shotPaid],
                ] as const
              ).map(([key, image], i) => (
                <li key={key} className="land-step reveal">
                  <span className="land-step-num" aria-hidden="true">
                    {i + 1}
                  </span>
                  <h3 className="m-0 text-[1.375rem] leading-tight font-semibold tracking-[-0.01em]">
                    {t(`landing.how.${key}.title`)}
                  </h3>
                  <p className="land-secondary m-0">{t(`landing.how.${key}.p`)}</p>
                  <figure className="land-shot">
                    <LandingImage
                      image={image}
                      alt={t(`landing.how.${key}.alt`)}
                      sizes="(min-width: 56rem) 20rem, 80vw"
                    />
                  </figure>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* 5. Why it matters */}
        <section aria-labelledby="why-title" className="land-section">
          <div className="land-wrap land-split flip">
            <div className="reveal grid gap-5">
              <h2 id="why-title" className="land-display-md">
                {t("landing.why.title")}
              </h2>
              <p className="land-lede">{t("landing.why.p1")}</p>
              <p className="land-lede">{t("landing.why.p2")}</p>
            </div>
            <figure className="land-photo tilt-b reveal">
              <LandingImage
                image={IMG.street}
                alt={t("landing.alt.street")}
                sizes="(min-width: 56rem) 30rem, 100vw"
              />
            </figure>
          </div>
        </section>

        {/* 6. What keeps it safe: only what the system really does */}
        <section aria-labelledby="safe-title" className="land-section">
          <div className="land-wrap">
            <div className="reveal grid gap-4">
              <h2 id="safe-title" className="land-display-md">
                {t("landing.safe.title")}
              </h2>
              <p className="land-lede">{t("landing.safe.intro")}</p>
            </div>
            <ul className="land-checks">
              {(["i1", "i2", "i3", "i4", "i5"] as const).map((k) => (
                <li key={k} className="reveal">
                  <BadgeCheck
                    aria-hidden="true"
                    size={24}
                    strokeWidth={1.75}
                    className="text-[var(--land-accent-text)]"
                  />
                  <span>{t(`landing.safe.${k}`)}</span>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* 7. Final call to action */}
        <section aria-labelledby="cta-title" className="land-section">
          <div className="land-wrap reveal grid justify-items-start gap-6">
            <h2 id="cta-title" className="land-display">
              {t("landing.cta.title")}
            </h2>
            <p className="land-lede">{t("landing.cta.p")}</p>
            <div className="land-actions">
              <a href={demoHref} className="land-btn press">
                {t("landing.tryDemo")}
              </a>
              {env.repoUrl ? (
                <a
                  href={env.repoUrl}
                  className="land-link"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {t("landing.cta.repo")}
                  <span className="sr-only"> ({t("landing.newTab")})</span>
                </a>
              ) : null}
            </div>
          </div>
        </section>
      </main>

      <footer className="land-section" style={{ borderTop: "1px solid var(--land-line)" }}>
        <div className="land-wrap grid gap-3">
          <p className="m-0 font-semibold">{t("landing.footer.madeBy", { team: env.teamName })}</p>
          <p className="land-secondary m-0">{t("landing.footer.event")}</p>
          {credits ? (
            <section aria-labelledby="credits-title" className="grid gap-1">
              <h2
                id="credits-title"
                className="land-secondary m-0 font-semibold text-[var(--type-secondary-size)]"
              >
                {t("landing.footer.credits")}
              </h2>
              <p className="land-secondary m-0 whitespace-pre-line text-[var(--type-secondary-size)]">
                {credits}
              </p>
            </section>
          ) : null}
        </div>
      </footer>
    </div>
  );
}
