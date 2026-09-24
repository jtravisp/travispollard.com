'use client';

/**
 * Dark/light toggle. One button, one instance, no popup.
 *
 * The palette menu this replaces was broken on desktop and worked on mobile,
 * which is a strange enough symptom to be worth recording. `themeMenu` was a
 * single JSX expression rendered twice -- once in the desktop cluster, once in
 * the mobile one -- and both copies carried `ref={themeRef}`. One ref object,
 * two DOM nodes: React set it for each in turn and the last commit won, so
 * `themeRef.current` held the mobile wrapper.
 *
 * The document `mousedown` handler then asked "is this click inside
 * `themeRef.current`?" On desktop that was always no, because the visible menu
 * was the other node. So it closed the menu on mousedown, React unmounted the
 * list before mouseup, and the click event never fired at all -- the handler
 * that writes `data-theme` was never reached. On mobile the ref happened to
 * hold the visible wrapper, `contains()` returned true, and it worked.
 *
 * A single button with no outside-click handler cannot have that bug, or the
 * "both menus open at once" one that came from sharing `themeOpen`.
 *
 * It reads the live attribute rather than keeping its own source of truth: the
 * inline script in `app/layout.tsx` has already decided the theme before this
 * component ever mounts, and a `useState('dark')` here would disagree with it
 * for one render on every light-theme load.
 */

import { Moon, Sun } from 'lucide-react';
import { useEffect, useState } from 'react';

export type Theme = 'dark' | 'light';

export const THEME_STORAGE_KEY = 'theme';

export default function ThemeToggle({ className = '' }: { className?: string }) {
  // Starts null so the first paint renders no icon rather than the wrong one.
  const [theme, setTheme] = useState<Theme | null>(null);

  useEffect(() => {
    const current = document.documentElement.getAttribute('data-theme');
    setTheme(current === 'light' ? 'light' : 'dark');
  }, []);

  const toggle = () => {
    const next: Theme = theme === 'light' ? 'dark' : 'light';
    setTheme(next);
    document.documentElement.setAttribute('data-theme', next);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // Private mode, or storage disabled. The toggle still works for this
      // page view; it just will not be remembered.
    }
  };

  // `suppressHydrationWarning` because the icon is deliberately absent on the
  // server and present after mount.
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={theme === 'light' ? 'Switch to dark theme' : 'Switch to light theme'}
      title={theme === 'light' ? 'Switch to dark theme' : 'Switch to light theme'}
      className={`btn btn-ghost btn-sm btn-square text-base-content/80 hover:text-base-content focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-base-content ${className}`}
      suppressHydrationWarning
    >
      {theme === 'light' ? (
        <Moon size={18} aria-hidden="true" />
      ) : theme === 'dark' ? (
        <Sun size={18} aria-hidden="true" />
      ) : (
        <span className="block h-[18px] w-[18px]" aria-hidden="true" />
      )}
    </button>
  );
}
