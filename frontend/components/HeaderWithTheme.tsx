// components/HeaderWithTheme.tsx
'use client';

import { Menu, X } from 'lucide-react';
import Link from 'next/link';
import { useEffect, useState } from 'react';

export default function HeaderWithTheme() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [theme, setTheme] = useState('business');

  // Restore the visitor's saved theme on mount (avoids a hydration mismatch)
  useEffect(() => {
    const saved = localStorage.getItem('theme');
    if (saved) {
      setTheme(saved);
      document.documentElement.setAttribute('data-theme', saved);
    }
  }, []);

  const handleThemeChange = (value: string) => {
    setTheme(value);
    document.documentElement.setAttribute('data-theme', value);
    localStorage.setItem('theme', value);
  };

  return (
    <header className="mb-10">
      <div className="flex flex-col sm:flex-row sm:items-center gap-4 sm:gap-8">
        <div className="flex justify-between items-center w-full sm:w-auto">
          <h1 className="text-4xl font-extrabold text-gray-100 font-sans">Travis Pollard</h1>
          <button
            className="sm:hidden text-gray-300"
            onClick={() => setMenuOpen(!menuOpen)}
            aria-label="Toggle menu"
          >
            {menuOpen ? <X size={24} /> : <Menu size={24} />}
          </button>
        </div>

        <div
          className={`${
            menuOpen ? 'flex' : 'hidden'
          } sm:flex flex-col sm:flex-row sm:items-center gap-4 w-full sm:flex-1`}
        >
          <nav className="w-full sm:w-auto sm:mr-auto">
            <ul className="flex flex-col sm:flex-row flex-wrap gap-2 sm:gap-4 text-sm font-medium text-gray-300 items-center sm:justify-start text-center">
              <li><Link href="/" className="link link-hover">Home</Link></li>
              <li><Link href="/resume" className="link link-hover">Resume</Link></li>
              <li><Link href="/projects" className="link link-hover">Projects</Link></li>
              <li><Link href="/stack" className="link link-hover">Stack</Link></li>
              <li><a href="https://github.com/jtravisp" target="_blank" rel="noopener noreferrer" className="link link-hover">GitHub</a></li>
              <li><a href="https://www.linkedin.com/in/travis-pollard" target="_blank" rel="noopener noreferrer" className="link link-hover">LinkedIn</a></li>
            </ul>
          </nav>

          <select
            id="theme-selector"
            aria-label="Color theme"
            className="select select-bordered select-sm w-full sm:w-auto"
            value={theme}
            onChange={(e) => handleThemeChange(e.target.value)}
          >
            <option value="business">Theme: Business</option>
            <option value="dracula">Theme: Dracula</option>
            <option value="synthwave">Theme: Synthwave</option>
            <option value="cyberpunk">Theme: Cyberpunk</option>
          </select>
        </div>
      </div>
    </header>
  );
}
