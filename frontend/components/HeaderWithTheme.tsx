// components/HeaderWithTheme.tsx
'use client';

import Link from 'next/link';
import { useEffect } from 'react';

export default function HeaderWithTheme() {
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
    <header className="flex flex-col sm:flex-row justify-between items-center mb-10">
      <h1 className="text-4xl font-extrabold text-gray-100 font-sans">Travis Pollard</h1>
      <nav>
        <ul className="flex flex-wrap gap-4 text-sm font-medium text-gray-300">
          <li><Link href="/" className="link link-hover">Home</Link></li>
          <li><Link href="/resume" className="link link-hover">Resume</Link></li>
          <li><a href="https://www.linkedin.com/in/travis-pollard" target="_blank" className="link link-hover">LinkedIn</a></li>
          <li><a href="https://medium.com/@travis_17385" target="_blank" className="link link-hover">Medium</a></li>
          <li><Link href="/bikeride" className="link link-hover">Bike Ride Planner</Link></li>
        </ul>
      </nav>
      <select id="theme-selector" className="select select-bordered select-sm mt-4 sm:mt-0">
        <option value="business" selected>Theme: Business</option>
        <option value="dracula">Theme: Dracula</option>
        <option value="synthwave">Theme: Synthwave</option>
        <option value="cyberpunk">Theme: Cyberpunk</option>
      </select>
    </header>
  );
}
