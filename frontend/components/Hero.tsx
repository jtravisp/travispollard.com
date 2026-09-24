'use client';

/**
 * Text left, photograph right, with one muted `$ whoami` line above the
 * eyebrow. Chosen on 2026-09-24 over a centred layout: at 1440 it puts the
 * Featured Projects heading inside the fold where the centred one pushed it
 * below, and the terminal nod stays a single quiet line rather than chrome.
 *
 * What it drops, deliberately:
 *
 * - **The h1 that repeated the name.** The header already says "Travis
 *   Pollard" 80px above. The h1 is the role now, which is also the thing a
 *   hiring manager is scanning for.
 * - **The terminal block.** Four lines of monospace chrome to deliver one
 *   sentence. The value line says the same thing in the body font, and the
 *   terminal motif still owns /projects where it means something.
 * - **The third button.** Contact moves to the footer as a mailto. Two
 *   buttons, one filled and one outlined, is a choice; three peers is a menu.
 *
 * On a phone the photo stacks above the text (flex-col-reverse), still
 * left-aligned with everything below it.
 */

import Link from 'next/link';
import Headshot from './Headshot';
import { site } from '@/content/site';

function Whoami() {
  return (
    // 70% is the floor for text on either theme: measured on rendered
    // pixels, 45% was 2.84:1 on light and 60% was 4.44:1. The prompt
    // character is decoration, so it alone goes lighter and is hidden from
    // assistive tech.
    <p className="mb-3 font-mono text-sm text-base-content/70">
      <span aria-hidden="true" className="text-base-content/35">
        $
      </span>{' '}
      whoami
    </p>
  );
}

function Eyebrow() {
  return <p className="mb-2 text-base text-base-content/70">Hi, I&apos;m Travis</p>;
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
function RingedPhoto() {
  return (
    <div
      className="relative w-56 shrink-0 rounded-full p-[3px] sm:w-64 lg:w-80"
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
  return (
    <section className="mb-24 flex flex-col-reverse items-center gap-12 pt-4 lg:flex-row lg:justify-between lg:gap-16 lg:pt-10">
      <div className="w-full lg:flex-1">
        <Whoami />
        <Eyebrow />
        <Title />
        <ValueLine className="max-w-xl" />
        <Buttons className="mt-8" />
      </div>
      <RingedPhoto />
    </section>
  );
}
