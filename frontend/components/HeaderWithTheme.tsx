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
 *
 * **Apps menu (2026-10).** By the time a third app (Austin Food Scores) was
 * due, the bar held seven links and measured 821px of its 848px row -- the
 * container is `max-w-4xl`, so that is the row at every desktop width, not just
 * `lg`. One more external link needs ~160px; it would have brought the wrap
 * back. The links also mixed two kinds of destination: pages about Travis, and
 * apps he built. So the apps moved behind one "Apps" disclosure button, the bar
 * dropped well under its budget, and each future app costs no bar width at all.
 *
 * It is a *disclosure* (button + `aria-expanded` + a list of links), not an
 * ARIA `menu`: WAI-ARIA's guidance for site navigation is the disclosure
 * pattern, because `role="menu"` promises application-style arrow-key handling
 * that a list of links does not need and screen readers then expect. Tab moves
 * through the links; Escape closes and returns focus to the button; a click
 * outside, tabbing out, or navigating closes it. In the mobile drawer there is
 * no second toggle -- the apps are a labelled group under the page links.
 */

import { ArrowUpRight, ChevronDown, Github, Linkedin, Menu, X } from 'lucide-react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
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
];

/** Things Travis built that you can use, behind the "Apps" disclosure. */
const APPS: NavItem[] = [
  { href: '/cfb', label: 'CFB Forecast' },
  { href: 'https://ncoer.travispollard.com', label: 'NCOER Writer', external: true },
  { href: 'https://austinfood.travispollard.com', label: 'Austin Food Scores', external: true },
];

type Variant = 'bar' | 'drawer' | 'menu';

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
  const [appsOpen, setAppsOpen] = useState(false);
  const appsRef = useRef<HTMLLIElement>(null);
  const appsButtonRef = useRef<HTMLButtonElement>(null);

  const pathname = usePathname();
  // `trailingSlash: true` in next.config.ts, so a live path is "/resume/".
  const here = pathname?.replace(/\/+$/, '') || '/';

  // A drawer (or Apps list) that survives navigation would cover the page it just opened.
  useEffect(() => {
    setMenuOpen(false);
    setAppsOpen(false);
  }, [pathname]);

  // A click anywhere outside the Apps disclosure closes it. Listening only
  // while it is open keeps this off every other click on the page.
  useEffect(() => {
    if (!appsOpen) return;
    const onPointerDown = (e: PointerEvent) => {
      if (!appsRef.current?.contains(e.target as Node)) setAppsOpen(false);
    };
    document.addEventListener('pointerdown', onPointerDown);
    return () => document.removeEventListener('pointerdown', onPointerDown);
  }, [appsOpen]);

  // Escape closes the drawer. The theme control is a plain button now, so
  // there is no popup left to dismiss and no outside-click handler to get
  // wrong -- which is what the old one did. See ThemeToggle.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      setMenuOpen(false);
      // Return focus to the button only if it was inside the Apps list;
      // otherwise Escape elsewhere on the page would pull focus into the header.
      if (appsRef.current?.contains(document.activeElement)) appsButtonRef.current?.focus();
      setAppsOpen(false);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  // Exact match, or a page beneath it: /music/<slug>/ still marks "Music".
  const isCurrent = (item: NavItem) =>
    !item.external && (here === item.href || here.startsWith(`${item.href}/`));
  const appsCurrent = APPS.some(isCurrent);

  const renderNavLink = (item: NavItem, variant: Variant = 'bar') => {
    const current = isCurrent(item);
    const className = [
      'link link-hover inline-flex items-center gap-1 whitespace-nowrap',
      FOCUS,
      variant === 'drawer' ? 'py-2 text-base' : '',
      // In the Apps list each link is a full-width row with the glyph at the end.
      variant === 'menu' ? 'w-full justify-between px-3 py-2 hover:bg-base-300' : '',
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
            <li
              ref={appsRef}
              className="relative"
              // Tabbing past the last app closes the list rather than leaving it
              // open over the page with focus somewhere else.
              onBlur={(e) => {
                if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setAppsOpen(false);
              }}
            >
              <button
                ref={appsButtonRef}
                type="button"
                aria-expanded={appsOpen}
                aria-controls="apps-nav"
                onClick={() => setAppsOpen((open) => !open)}
                className={[
                  'link link-hover inline-flex items-center gap-1 whitespace-nowrap',
                  FOCUS,
                  appsCurrent
                    ? 'font-semibold text-base-content underline underline-offset-4 decoration-2'
                    : 'text-base-content/80',
                ].join(' ')}
              >
                Apps
                <ChevronDown
                  size={14}
                  aria-hidden="true"
                  className={`shrink-0 opacity-70 transition-transform ${appsOpen ? 'rotate-180' : ''}`}
                />
              </button>
              {appsOpen && (
                <ul
                  id="apps-nav"
                  className="absolute right-0 top-full z-50 mt-3 w-60 rounded-box border border-base-300 bg-base-200 p-1.5 shadow-lg"
                >
                  {APPS.map((item) => (
                    <li key={item.href}>{renderNavLink(item, 'menu')}</li>
                  ))}
                </ul>
              )}
            </li>
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
              <li key={item.href}>{renderNavLink(item, 'drawer')}</li>
            ))}
          </ul>
          {/* No nested toggle on mobile: the apps are a labelled group. */}
          <p
            id="apps-heading-mobile"
            className="mt-4 text-xs font-semibold uppercase tracking-wide text-base-content/60"
          >
            Apps
          </p>
          <ul aria-labelledby="apps-heading-mobile" className="flex flex-col divide-y divide-base-300">
            {APPS.map((item) => (
              <li key={item.href}>{renderNavLink(item, 'drawer')}</li>
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
