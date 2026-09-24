'use client';

/**
 * Two hero layouts behind one constant, for choosing between.
 *
 * `HERO_VARIANT` picks the layout and `HERO_SHOW_WHOAMI` decides whether the
 * single muted terminal line survives above the eyebrow. Both are constants
 * rather than props because exactly one of these ships; once the choice is
 * made, the loser and this comment go.
 *
 * What both drop, deliberately:
 *
 * - **The h1 that repeated the name.** The header already says "Travis
 *   Pollard" 80px above. The h1 is the role now, which is also the thing a
 *   hiring manager is scanning for.
 * - **The terminal block.** Four lines of monospace chrome to deliver one
 *   sentence. The value line says the same thing in the body font, and the
 *   terminal motif still owns /projects where it means something.
 * - **The third button.** Contact moves to the footer as a mailto. Two
 *   buttons, one filled and one outlined, is a choice; three peers is a menu.
 */

import Link from 'next/link';
import Headshot from './Headshot';
import { site } from '@/content/site';

export type HeroVariant = 'A' | 'B';

/** 'A' = text left, photo right. 'B' = centred, photo on top. */
export const HERO_VARIANT: HeroVariant = 'A';

/** The single muted `$ whoami` line above the eyebrow. */
export const HERO_SHOW_WHOAMI = true;

function Whoami() {
  if (!HERO_SHOW_WHOAMI) return null;
  return (
    <p className="mb-3 font-mono text-sm text-base-content/45">
      <span className="text-base-content/30">$</span> whoami
    </p>
  );
}

function Eyebrow() {
  return <p className="mb-2 text-base text-base-content/60">Hi, I&apos;m Travis</p>;
}

function Title() {
  return (
    <h1 className="mb-4 text-4xl font-bold tracking-tight sm:text-5xl lg:text-6xl">
      Platform Engineer
    </h1>
  );
}

function ValueLine({ className = '' }: { className?: string }) {
  return (
    <p className={`text-lg leading-relaxed text-base-content/75 ${className}`}>
      {site.valueStatement}
    </p>
  );
}

function Buttons({ className = '' }: { className?: string }) {
  return (
    <div className={`flex flex-wrap gap-3 ${className}`}>
      <Link href="/resume" className="btn btn-primary">
        View Resume
      </Link>
      <Link href="/projects" className="btn btn-outline">
        See Projects
      </Link>
    </div>
  );
}

/**
 * The accent ring and its glow.
 *
 * One ring, one colour, and the glow is a wide low-alpha shadow in the same
 * hue rather than a second border -- two rings reads as a target.
 * `color-mix` against `--color-primary` keeps it on the accent when the theme
 * swaps the accent for its darker light-mode value.
 */
function RingedPhoto({ size }: { size: 'lg' | 'md' }) {
  return (
    <div
      className={`relative shrink-0 rounded-full p-[3px] ${
        size === 'lg' ? 'w-56 sm:w-64 lg:w-80' : 'w-40 sm:w-48'
      }`}
      style={{
        background: 'var(--color-primary)',
        boxShadow: '0 0 60px -12px color-mix(in oklab, var(--color-primary) 65%, transparent)',
      }}
    >
      <Headshot className="!w-full rounded-full" />
    </div>
  );
}

export default function Hero() {
  if (HERO_VARIANT === 'B') {
    return (
      <section className="mb-24 flex flex-col items-center pt-6 text-center sm:pt-10">
        <RingedPhoto size="md" />
        <div className="mt-8 max-w-2xl">
          <Whoami />
          <Eyebrow />
          <Title />
          <ValueLine className="mx-auto max-w-xl" />
          <Buttons className="mt-8 justify-center" />
        </div>
      </section>
    );
  }

  return (
    <section className="mb-24 flex flex-col-reverse items-center gap-12 pt-4 lg:flex-row lg:justify-between lg:gap-16 lg:pt-10">
      <div className="w-full lg:flex-1">
        <Whoami />
        <Eyebrow />
        <Title />
        <ValueLine className="max-w-xl" />
        <Buttons className="mt-8" />
      </div>
      <RingedPhoto size="lg" />
    </section>
  );
}
