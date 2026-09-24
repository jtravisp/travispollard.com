'use client';

/**
 * Text left, photograph right: eyebrow, role, one value line, two buttons.
 * Chosen on 2026-09-24 over a centred layout: at 1440 it puts the Featured
 * Projects heading inside the fold where the centred one pushed it below.
 * The `$ whoami` line that sat above the eyebrow is gone too -- the hero is
 * identity and value only, and the terminal motif lives on /projects.
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

function Eyebrow() {
  return <p className="mb-2 text-base text-base-content/70">Hi, I&apos;m Travis</p>;
}

function Title() {
  return (
    // Gradient text: white to neutral-400 on the dark theme. The light theme
    // cannot take the same stops -- neutral-400 on the light surface is under
    // 3:1 even at this size -- so it fades from the text colour to 70% of it.
    // The gradient is on an inline span with box-decoration-clone, so each
    // line of the wrapped heading gets the full fade across its own words.
    // On the block h1 it spanned the whole column and most of the fade fell
    // in empty space. pb-1 keeps the "g" descender inside the clip.
    <h1 className="mb-3 text-4xl font-bold tracking-tight sm:text-5xl lg:text-6xl">
      <span className="box-decoration-clone bg-linear-to-r from-base-content to-base-content/70 bg-clip-text pb-1 text-transparent dark:from-white dark:to-neutral-400">
        Platform Engineer
      </span>
    </h1>
  );
}

function ValueLine({ className = '' }: { className?: string }) {
  return (
    <p className={`text-lg leading-relaxed text-base-content/75 ${className}`}>
      {/* A hyphenated word stays on one line: at 1440 the browser broke
          "AI-driven" after its hyphen and started the second line on
          "driven". Wrapping between words is untouched. */}
      {site.valueStatement.split(/(\S+-\S+)/).map((part, i) =>
        i % 2 === 1 ? (
          <span key={i} className="whitespace-nowrap">
            {part}
          </span>
        ) : (
          part
        ),
      )}
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
 * The photograph, backlit.
 *
 * No ring: a large, heavily blurred, low-opacity coral disc sits behind the
 * image as ambient light instead of a hard edge around it. `isolate` gives it
 * its own stacking context, so `-z-10` puts it behind the photo and not behind
 * the page background, where it would vanish.
 *
 * The photo is grayscale at 90% and comes up to full colour on hover. On a
 * touch screen there is no hover, so a phone always sees the grayscale
 * version; reduced-motion users get the change without the transition.
 */
function BacklitPhoto() {
  return (
    <div className="relative isolate w-56 shrink-0 sm:w-64 lg:w-80">
      <div
        aria-hidden="true"
        className="absolute -inset-10 -z-10 rounded-full bg-primary opacity-25 blur-3xl"
      />
      <Headshot className="!w-full rounded-full opacity-90 grayscale transition-all duration-300 hover:opacity-100 hover:grayscale-0 motion-reduce:transition-none" />
    </div>
  );
}

export default function Hero() {
  return (
    <section className="mb-32 flex flex-col-reverse items-center gap-12 pt-4 lg:flex-row lg:justify-between lg:gap-16 lg:pt-10">
      <div className="w-full lg:flex-1">
        <Eyebrow />
        <Title />
        <ValueLine className="max-w-xl" />
        <Buttons className="mt-8" />
      </div>
      <BacklitPhoto />
    </section>
  );
}
