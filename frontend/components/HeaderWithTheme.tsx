// components/HeaderWithTheme.tsx
'use client';

import { Menu, X } from 'lucide-react';
import Link from 'next/link';
import { useEffect, useState } from 'react';

export default function HeaderWithTheme() {
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const selector = document.getElementById('theme-selector') as HTMLSelectElement | null;
    if (selector) {
      selector.addEventListener('change', (e) => {
        const target = e.target as HTMLSelectElement;
        document.documentElement.setAttribute('data-theme', target.value);
      });
    }
  }, []);

  return (
    <header className="mb-10">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
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
          } sm:flex flex-col sm:flex-row sm:items-center gap-4 w-full sm:w-auto`}
        >
          <nav className="w-full sm:w-auto">
            <ul className="flex flex-col sm:flex-row flex-wrap gap-2 sm:gap-4 text-sm font-medium text-gray-300 items-center text-center">
              <li><Link href="/" className="link link-hover">Home</Link></li>
              <li><Link href="/resume" className="link link-hover">Resume</Link></li>
              <li><Link href="/projects" className="link link-hover">Projects</Link></li>
              <li><a href="https://www.linkedin.com/in/travis-pollard" target="_blank" className="link link-hover">LinkedIn</a></li>
              <li><a href="https://medium.com/@travis_17385" target="_blank" className="link link-hover">Medium</a></li>
              <li><Link href="/bikeride" className="link link-hover">Bike Ride Planner</Link></li>
            </ul>
          </nav>

          <select
            id="theme-selector"
            className="select select-bordered select-sm w-full sm:w-auto"
          >
            <option value="business" selected>Theme: Business</option>
            <option value="dracula">Theme: Dracula</option>
            <option value="synthwave">Theme: Synthwave</option>
            <option value="cyberpunk">Theme: Cyberpunk</option>
          </select>
        </div>
      </div>
    </header>
  );
}
