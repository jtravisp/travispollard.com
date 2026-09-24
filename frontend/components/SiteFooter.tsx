/**
 * Small and quiet.
 *
 * The old footer was a filled `footer-center` bar in `bg-neutral` -- the same
 * dark surface the terminal blocks use, which made the bottom of the page read
 * as one more container. A rule and four muted links say the same thing without
 * adding a third container style to a page that is allowed two.
 *
 * This is also where Contact went when the hero dropped to two buttons.
 */

import { site } from '@/content/site';

export default function SiteFooter() {
  return (
    <footer className="border-t border-base-300 pt-8 pb-4">
      <div className="flex flex-wrap items-center justify-between gap-x-8 gap-y-3 text-sm text-base-content/60">
        <p>&copy; {new Date().getFullYear()} {site.name}</p>
        <ul className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <li>
            <a href={`mailto:${site.email}`} className="hover:text-primary">
              {site.email}
            </a>
          </li>
          <li>
            <a
              href={site.github}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-primary"
            >
              GitHub
            </a>
          </li>
          <li>
            <a
              href={site.linkedin}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-primary"
            >
              LinkedIn
            </a>
          </li>
        </ul>
      </div>
    </footer>
  );
}
