'use client';

import Certifications from '@/components/Certifications';
import HeaderWithTheme from '@/components/HeaderWithTheme';
import Hero from '@/components/Hero';
import SiteFooter from '@/components/SiteFooter';
import VisitorCounter from '@/components/VisitorCounter';
import { featuredProjects, isLive, visibleSummary, visibleTags } from '@/content/projects';
import { writing } from '@/content/site';
import Link from 'next/link';

export default function Home() {
  return (
    <main className="min-h-screen bg-base-100 text-base-content">
      <div className="mx-auto max-w-4xl px-6 py-10">
        <HeaderWithTheme />

        <Hero />

        <Certifications />

        {/* Featured projects.
            A stacked list rather than three cards: it gives each project room
            for a sentence that says something, it does not go ragged when a
            fourth is added, and three equal-width bordered boxes is the single
            most template-looking shape on the internet.

            Tags are middot-separated text. The only link styling is one arrow
            per destination. */}
        <section className="mb-24">
          <div className="mb-8 flex items-baseline justify-between gap-4">
            <h2 className="text-2xl font-bold tracking-tight">Featured Projects</h2>
            <Link
              href="/projects"
              className="text-sm text-base-content/70 hover:text-primary"
            >
              All projects &rarr;
            </Link>
          </div>

          <ul className="divide-y divide-base-300 border-t border-base-300">
            {featuredProjects.map((project) => (
              <li key={project.id} className="py-7">
                <h3 className="flex items-center gap-3 text-lg font-semibold">
                  {project.cardTitle}
                  {isLive(project) && (
                    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-primary">
                      <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-primary" />
                      Live
                    </span>
                  )}
                </h3>
                {visibleSummary(project) && (
                  <p className="mt-1.5 max-w-2xl text-base-content/75">
                    {visibleSummary(project)}
                  </p>
                )}
                {visibleTags(project).length > 0 && (
                  <p className="mt-3 font-mono text-xs text-base-content/70">
                    {visibleTags(project).join(' · ')}
                  </p>
                )}
                {project.links.length > 0 && (
                  <p className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-sm">
                    {project.links.map((link) => (
                      <a
                        key={link.url}
                        href={link.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-base-content/70 hover:text-primary"
                      >
                        {link.label === 'live' ? 'View project' : link.label} &rarr;
                        <span className="sr-only"> ({project.cardTitle}, opens in a new tab)</span>
                      </a>
                    ))}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </section>

        {/* Writing. A list, not cards. Adding a post is one object in
            content/site.ts. */}
        <section className="mb-24">
          <h2 className="mb-8 text-2xl font-bold tracking-tight">Writing</h2>
          <ul className="divide-y divide-base-300 border-t border-base-300">
            {writing.map((post) => (
              <li key={post.url} className="py-5">
                <a
                  href={post.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="group flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1"
                >
                  <span className="font-medium group-hover:text-primary">{post.title}</span>
                  <span className="text-sm text-base-content/70">
                    {post.outlet}
                    {post.year ? ` · ${post.year}` : ''}
                  </span>
                </a>
              </li>
            ))}
          </ul>
          <p className="mt-6 text-sm">
            <a
              href="https://medium.com/@travis_17385"
              target="_blank"
              rel="noopener noreferrer"
              className="text-base-content/70 hover:text-primary"
            >
              More on Medium &rarr;
            </a>
          </p>
        </section>

        <SiteFooter />
        <VisitorCounter />
      </div>

      <Link href="/campout" className="hidden" aria-hidden="true">
        Campout
      </Link>
    </main>
  );
}
