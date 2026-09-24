'use client';

import HeaderWithTheme from '@/components/HeaderWithTheme';
import Headshot from '@/components/Headshot';
import VisitorCounter from '@/components/VisitorCounter';
import { featuredProjects } from '@/content/projects';
import { site, writing } from '@/content/site';
import { ArrowUpRight } from 'lucide-react';
import Link from 'next/link';
import Techstack from './techstack';

export default function Home() {
  return (
    <main className="min-h-screen bg-base-100 text-base-content">
      <div className="max-w-5xl mx-auto px-4 py-10">

        {/* Header */}
        <HeaderWithTheme />

        {/* Hero.
            Two columns at lg rather than a centred stack: the portrait used to
            sit under the terminal card at 450px wide, which pushed the calls to
            action off a 1440x900 screen entirely. Name, role, value statement,
            and both buttons now land above the fold. */}
        <section className="mb-16 flex flex-col-reverse items-center gap-8 lg:flex-row lg:items-center lg:justify-between lg:gap-12">
          <div className="w-full lg:flex-1">
            <h1 className="mb-4 text-4xl font-extrabold tracking-tight sm:text-5xl">
              {site.name}
            </h1>

            <div className="mockup-code w-full max-w-xl text-left [&_pre]:whitespace-pre-wrap">
              <pre data-prefix="$">
                <code className="text-info">whoami</code>
              </pre>
              <pre data-prefix=">" className="text-warning">
                <code>
                  <a href={`mailto:${site.email}`} className="link">
                    {site.email}
                  </a>
                </code>
              </pre>
              <pre data-prefix=">" className="text-warning">
                <code>{site.role}</code>
              </pre>
              <pre data-prefix=">" className="text-warning">
                <code>{site.valueStatement}</code>
              </pre>
            </div>

            {/* "View My Resume" and "Download Resume (PDF)" sat side by side
                asking the same question twice. One Resume button; the PDF is on
                the page it belongs to. */}
            <div className="mt-6 flex flex-wrap gap-3">
              <Link href="/resume" className="btn btn-primary">
                Resume
              </Link>
              <Link href="/projects" className="btn btn-accent">
                Projects
              </Link>
              <a href={`mailto:${site.email}`} className="btn btn-outline">
                Contact
              </a>
            </div>
          </div>

          <Headshot className="shrink-0" />
        </section>

        {/* Featured projects. Same objects the /projects page renders. */}
        <section className="mb-16">
          <div className="mb-4 flex items-baseline justify-between gap-4">
            <h2 className="text-xl font-bold">Featured Projects</h2>
            <Link href="/projects" className="link link-hover text-sm text-base-content/70">
              All projects
            </Link>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {featuredProjects.map((project) => (
              <article
                key={project.id}
                className="card flex flex-col gap-3 border border-base-300 bg-base-200 p-5"
              >
                <h3 className="text-lg font-semibold">{project.cardTitle}</h3>
                <p className="text-sm text-base-content/80">{project.summary}</p>

                <ul className="flex flex-wrap gap-1.5">
                  {project.tags.map((tag) => (
                    <li key={tag} className="badge badge-sm badge-outline font-mono text-xs">
                      {tag}
                    </li>
                  ))}
                </ul>

                {project.links.length > 0 && (
                  <ul className="mt-auto flex flex-wrap gap-x-4 gap-y-1 pt-1 text-sm">
                    {project.links.map((link) => (
                      <li key={link.url}>
                        <a
                          href={link.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="link link-primary inline-flex items-center gap-1"
                        >
                          {link.label}
                          <ArrowUpRight size={13} aria-hidden="true" className="opacity-70" />
                          <span className="sr-only">
                            {project.cardTitle} (opens in a new tab)
                          </span>
                        </a>
                      </li>
                    ))}
                  </ul>
                )}
              </article>
            ))}
          </div>
        </section>

        {/* Writing. Adding a post is one object in content/site.ts.
            Full width, not max-w-3xl: it was the only section on the page that
            was centred narrower than the rest, so its heading sat 110px right
            of every other heading at 1440. */}
        <section className="w-full mb-16">
          <h2 className="text-xl font-bold mb-4">Writing</h2>
          <div className="flex flex-col gap-3">
            {writing.map((post) => (
              <a
                key={post.url}
                href={post.url}
                target="_blank"
                rel="noopener noreferrer"
                className="card bg-base-200 hover:bg-base-300 transition-colors p-4 border-l-4 border-primary"
              >
                <span className="font-semibold">{post.title}</span>
                <span className="text-sm opacity-70">{post.outlet}</span>
              </a>
            ))}
          </div>
        </section>

        <section className="flex flex-col items-center gap-6 mb-16 text-center">
          <Techstack />
        </section>

        {/* Certification badges.
            No mask-squircle. All three are transparent PNGs of different aspect
            ratios, so the mask clipped the Terraform wordmark's right edge
            while doing nothing for the two hexagonal AWS badges. Matching them
            on height instead lines them up without cropping any of them.

            The white chip is not decoration either: the Terraform lockup is
            near-black artwork on transparency, so on Business and Dracula it
            was black on near-black and the word was gone. These are vendor
            brand assets drawn for a light background, and giving all three the
            same light chip is both legible and what the brand guidelines
            assume -- rather than tinting one badge and not the others. */}
        <section className="flex flex-wrap items-center justify-center gap-6 mb-20">
          {[
            { src: '/images/AWS%20CSA.png', alt: 'AWS Certified Solutions Architect - Associate badge' },
            { src: '/images/AWS%20Dev.png', alt: 'AWS Certified Developer - Associate badge' },
            { src: '/images/terraform.webp', alt: 'HashiCorp Certified: Terraform Associate badge' },
          ].map((badge) => (
            <div
              key={badge.src}
              className="flex h-[150px] w-[170px] items-center justify-center rounded-box bg-white p-4 shadow-md"
            >
              <img
                src={badge.src}
                alt={badge.alt}
                width={150}
                height={150}
                className="max-h-full w-auto object-contain"
              />
            </div>
          ))}
        </section>

        {/* Footer */}
        <footer className="footer footer-center p-6 bg-neutral text-neutral-content rounded-lg">
          <p>&copy; 2026 {site.name} - {site.location} - {site.email}</p>
        </footer>

        <VisitorCounter />

      </div>

      <Link href="/campout" className="hidden">Campout</Link>

    </main>
  );
}
