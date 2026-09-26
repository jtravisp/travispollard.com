// components/HeaderWithTheme.tsx
'use client';

/**
 * The site header.
 *
 * Three things were wrong with the version this replaces, and they compounded:
 *
 * 1. **Eight text links, a `text-4xl` name, and a `w-full sm:w-auto` select.**
 *    Together they needed roughly 1,150px of a 1,024px container, so LinkedIn
 *    wrapped to a second line at every desktop width anyone actually uses.
 * 2. **The breakpoint was `sm` (640px).** The full desktop bar was switched on
 *    384px before it fit, so the wrap was not an edge case -- it was every
 *    laptop.
 * 3. **`text-gray-100` and `text-gray-300` were hardcoded.** Those are
 *    near-white, which is fine on Business and Dracula and unreadable on
 *    Cyberpunk, whose `base-100` is bright yellow. A themeable site cannot name
 *    its own greys; `text-base-content` is the same colour on the dark themes
 *    and legible on the light one.
 *
 * So: the name drops to `text-xl` and links home (which is what retires the
 * "Home" link), the bar switches at `lg`, GitHub and LinkedIn become icon
 * buttons, and the theme select becomes a palette button. Five text links, two
 * icons and the palette measure ~870px at `lg`, which leaves real margin rather
 * than the 20px that made the old bar wrap on a scrollbar's width.
 */

import { ArrowUpRight, Github, Linkedin, Menu, X } from 'lucide-react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import ThemeToggle from './ThemeToggle';

type NavItem = {
  href: string;
  label: string;
  /** Opens in a new tab and renders the hint glyph. */
  external?: boolean;
};

const NAV: NavItem[] = [
  { href: '/resume', label: 'Resume' },
  { href: '/projects', label: 'Projects' },
  { href: '/stack', label: 'Stack' },
  { href: '/music', label: 'Music' },
  { href: '/status', label: 'Status' },
  { href: '/cfb', label: 'CFB Forecast' },
  { href: 'https://ncoer.travispollard.com', label: 'NCOER Writer', external: true },
];

/** Shared by the desktop bar and the drawer so focus is visible in both.
 *
 * `outline-base-content`, not `outline-primary`, for the reason the active-page
 * marker gives up its colour below: Business's primary measures 1.9:1 against
 * this background, and a focus ring nobody can see is the same as no focus ring.
 * Lighthouse does not catch this one, because it never tabs anything. */
const FOCUS =
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-base-content rounded';

export default function HeaderWithTheme() {
  const [menuOpen, setMenuOpen] = useState(false);

  const pathname = usePathname();
  // `trailingSlash: true` in next.config.ts, so a live path is "/resume/".
  const here = pathname?.replace(/\/+$/, '') || '/';

  // A drawer that survives navigation would cover the page it just opened.
  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  // Escape closes the drawer. The theme control is a plain button now, so
  // there is no popup left to dismiss and no outside-click handler to get
  // wrong -- which is what the old one did. See ThemeToggle.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenuOpen(false);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  const renderNavLink = (item: NavItem, onDrawer = false) => {
    // Exact match, or a page beneath it: /music/<slug>/ still marks "Music".
    const current =
      !item.external && (here === item.href || here.startsWith(`${item.href}/`));
    const className = [
      'link link-hover inline-flex items-center gap-1 whitespace-nowrap',
      FOCUS,
      onDrawer ? 'py-2 text-base' : '',
      // Not text-primary. Business's primary is a dark navy that measures
      // 1.9:1 as text on this background -- the active page would have been the
      // least readable item in the bar. Weight and a persistent underline mark
      // it instead, which were already the non-colour signals; dropping the
      // colour loses nothing and fixes the contrast.
      current
        ? 'font-semibold text-base-content underline underline-offset-4 decoration-2'
        : 'text-base-content/80',
    ].join(' ');

    if (item.external) {
      return (
        <a
          href={item.href}
          target="_blank"
          rel="noopener noreferrer"
          className={className}
        >
          {item.label}
          <ArrowUpRight size={14} aria-hidden="true" className="shrink-0 opacity-70" />
          <span className="sr-only">(opens in a new tab)</span>
        </a>
      );
    }

    return (
      <Link href={item.href} aria-current={current ? 'page' : undefined} className={className}>
        {item.label}
      </Link>
    );
  };

  const iconLinks = (
    <>
      <a
        href="https://github.com/jtravisp"
        target="_blank"
        rel="noopener noreferrer"
        aria-label="GitHub profile (opens in a new tab)"
        className={`btn btn-ghost btn-sm btn-square text-base-content/80 hover:text-base-content ${FOCUS}`}
      >
        <Github size={18} aria-hidden="true" />
      </a>
      <a
        href="https://www.linkedin.com/in/travis-pollard"
        target="_blank"
        rel="noopener noreferrer"
        aria-label="LinkedIn profile (opens in a new tab)"
        className={`btn btn-ghost btn-sm btn-square text-base-content/80 hover:text-base-content ${FOCUS}`}
      >
        <Linkedin size={18} aria-hidden="true" />
      </a>
    </>
  );

  return (
    <header className="mb-10">
      <div className="flex items-center gap-4">
        <Link
          href="/"
          aria-current={here === '/' ? 'page' : undefined}
          className={`text-xl font-bold tracking-tight text-base-content hover:underline hover:underline-offset-4 ${FOCUS}`}
        >
          Travis Pollard
        </Link>

        {/* Desktop bar. `lg` because that is where it measures, not `sm`. */}
        <nav aria-label="Main" className="ml-auto hidden lg:block">
          <ul className="flex items-center gap-5 text-sm font-medium">
            {NAV.map((item) => (
              <li key={item.href}>{renderNavLink(item)}</li>
            ))}
          </ul>
        </nav>
        <div className="hidden items-center gap-1 lg:flex">{iconLinks}</div>

        {/* One toggle node, rendered once at every width rather than once per
            breakpoint cluster. Two nodes sharing one ref is exactly what broke
            the control this replaces. */}
        <ThemeToggle className="ml-auto lg:ml-0" />

        <div className="flex items-center gap-1 lg:hidden">
          <button
            type="button"
            onClick={() => setMenuOpen((open) => !open)}
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={menuOpen}
            aria-controls="mobile-nav"
            className={`btn btn-ghost btn-sm btn-square text-base-content ${FOCUS}`}
          >
            {menuOpen ? <X size={22} aria-hidden="true" /> : <Menu size={22} aria-hidden="true" />}
          </button>
        </div>
      </div>

      {menuOpen && (
        <nav
          id="mobile-nav"
          aria-label="Main"
          className="mt-4 rounded-box border border-base-300 bg-base-200 p-4 lg:hidden"
        >
          <ul className="flex flex-col divide-y divide-base-300">
            {NAV.map((item) => (
              <li key={item.href}>{renderNavLink(item, true)}</li>
            ))}
          </ul>
          <div className="mt-3 flex items-center gap-1 border-t border-base-300 pt-3">
            {iconLinks}
          </div>
        </nav>
      )}
    </header>
  );
}
