'use client';

/**
 * The football section's own header.
 *
 * Not `HeaderWithTheme`. That one carries a site-wide theme selector that writes
 * `data-theme` onto `<html>`, and this section pins its own theme on a wrapper
 * element — so the selector would appear to do nothing here, which is worse than
 * not offering it. The link back to the rest of the site is what it replaces.
 *
 * Marking the current page is done with `aria-current` as well as colour,
 * because "which of these am I on" should not depend on distinguishing two
 * shades of orange.
 */

import Link from 'next/link';
import { usePathname } from 'next/navigation';

const SECTIONS = [
  { href: '/cfb', label: 'Next game' },
  { href: '/cfb/slate', label: 'Full slate' },
  { href: '/cfb/accuracy', label: 'Accuracy' },
  { href: '/cfb/models', label: 'Models' },
];

export default function CfbNav() {
  const pathname = usePathname();
  // `trailingSlash: true` in next.config.ts, so a live path is "/cfb/slate/".
  const here = pathname.replace(/\/+$/, '') || '/cfb';

  return (
    <header className="mb-8 border-b border-base-300 pb-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <Link href="/cfb" className="text-2xl font-extrabold tracking-tight">
          <span className="text-primary">Texas</span> Football Forecast
        </Link>
        <Link href="/" className="link link-hover text-sm text-base-content/60">
          ← travispollard.com
        </Link>
      </div>

      <nav className="mt-3">
        <ul className="flex flex-wrap gap-1">
          {SECTIONS.map((section) => {
            const current = here === section.href;
            return (
              <li key={section.href}>
                <Link
                  href={section.href}
                  aria-current={current ? 'page' : undefined}
                  className={
                    current
                      ? 'btn btn-sm btn-primary'
                      : 'btn btn-sm btn-ghost text-base-content/70'
                  }
                >
                  {section.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </header>
  );
}
