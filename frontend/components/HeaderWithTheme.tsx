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

import { ArrowUpRight, Check, Github, Linkedin, Menu, Palette, X } from 'lucide-react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';

const THEMES = [
  { value: 'business', label: 'Business' },
  { value: 'dracula', label: 'Dracula' },
  { value: 'synthwave', label: 'Synthwave' },
  { value: 'cyberpunk', label: 'Cyberpunk' },
] as const;

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
  const [themeOpen, setThemeOpen] = useState(false);
  const [theme, setTheme] = useState<string>('business');
  const themeRef = useRef<HTMLDivElement>(null);

  const pathname = usePathname();
  // `trailingSlash: true` in next.config.ts, so a live path is "/resume/".
  const here = pathname?.replace(/\/+$/, '') || '/';

  // Restore the visitor's saved theme on mount (avoids a hydration mismatch)
  useEffect(() => {
    const saved = localStorage.getItem('theme');
    if (saved) {
      setTheme(saved);
      document.documentElement.setAttribute('data-theme', saved);
    }
  }, []);

  // A drawer that survives navigation would cover the page it just opened.
  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  // Escape closes whichever is open, and a click outside closes the theme menu.
  // Without these the palette menu can only be dismissed by choosing something,
  // which makes "just looking" a destructive action.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      setThemeOpen(false);
      setMenuOpen(false);
    };
    const onClick = (e: MouseEvent) => {
      if (themeRef.current && !themeRef.current.contains(e.target as Node)) {
        setThemeOpen(false);
      }
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onClick);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onClick);
    };
  }, []);

  const handleThemeChange = useCallback((value: string) => {
    setTheme(value);
    document.documentElement.setAttribute('data-theme', value);
    localStorage.setItem('theme', value);
    setThemeOpen(false);
  }, []);

  const renderNavLink = (item: NavItem, onDrawer = false) => {
    const current = !item.external && here === item.href;
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

  const themeMenu = (
    <div className="relative" ref={themeRef}>
      <button
        type="button"
        onClick={() => setThemeOpen((open) => !open)}
        aria-label={`Color theme: ${THEMES.find((t) => t.value === theme)?.label ?? theme}`}
        aria-haspopup="menu"
        aria-expanded={themeOpen}
        className={`btn btn-ghost btn-sm btn-square text-base-content/80 hover:text-base-content ${FOCUS}`}
      >
        <Palette size={18} aria-hidden="true" />
      </button>
      {themeOpen && (
        <ul
          role="menu"
          aria-label="Color theme"
          className="absolute right-0 z-50 mt-2 min-w-40 rounded-box border border-base-300 bg-base-200 p-2 shadow-lg"
        >
          {THEMES.map((t) => (
            <li key={t.value} role="none">
              <button
                type="button"
                role="menuitemradio"
                aria-checked={theme === t.value}
                onClick={() => handleThemeChange(t.value)}
                className={`flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm text-base-content hover:bg-base-300 ${FOCUS}`}
              >
                <Check
                  size={14}
                  aria-hidden="true"
                  className={theme === t.value ? 'opacity-100' : 'opacity-0'}
                />
                {t.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
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
        <div className="hidden items-center gap-1 lg:flex">
          {iconLinks}
          {themeMenu}
        </div>

        {/* Below lg: the palette stays out, so changing theme does not cost a
            drawer open, and the hamburger carries the rest. */}
        <div className="ml-auto flex items-center gap-1 lg:hidden">
          {themeMenu}
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
