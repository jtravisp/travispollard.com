'use client';

import HeaderWithTheme from '@/components/HeaderWithTheme';
import PageIntro from '@/components/PageIntro';
import { cloudAiProjects, earlierWork, visibleItems, type Project } from '@/content/projects';
import { motion } from 'framer-motion';
import Link from 'next/link';
import { Typewriter } from 'react-simple-typewriter';
import { useEffect, useState } from 'react';

const TERMINAL = 'mockup-code w-full text-left text-base font-mono [&_pre]:whitespace-pre-wrap';

/**
 * A line that is a TODO renders as one.
 *
 * These exist so an unverified claim is visible rather than quietly confident.
 * Rendering them in the same grey as everything else would defeat the point, so
 * they get the warning colour the rest of the terminal reserves for output that
 * wants reading.
 */
function Line({ text }: { text: string }) {
  const isTodo = text.startsWith('TODO(travis)') || text.includes('TODO(travis)');
  return (
    <pre data-prefix=">" className={isTodo ? 'text-warning' : undefined}>
      <code>{text}</code>
    </pre>
  );
}

function ProjectBlock({ project, index }: { project: Project; index: number }) {
  return (
    <motion.div
      className={TERMINAL}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: Math.min(index, 4) * 0.1 }}
    >
      <pre data-prefix="$" className="text-info">
        <code>{`# ${project.title}`}</code>
      </pre>
      {visibleItems(project).map((item, i) => (
        <Line key={i} text={item} />
      ))}
      {project.links.length > 0 && (
        <pre data-prefix=">" className="text-info">
          <code>
            {project.links.map((link, i) => (
              <span key={link.url}>
                {i > 0 && ' | '}
                <a
                  href={link.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="link"
                >
                  {link.label}: {link.url.replace('https://', '')}
                </a>
              </span>
            ))}
          </code>
        </pre>
      )}
    </motion.div>
  );
}

/**
 * Section B, collapsed on a phone and open on a desktop.
 *
 * Six terminal blocks used to cover identity, monitoring, imaging, device
 * management, internal tools and metrics, above the cloud work for part of this
 * page's life. It is one block now, and below -- but on a phone even one block
 * is eight paragraphs of pre-cloud history standing between the projects
 * someone came for and the bottom of the page.
 *
 * The open state is set from `matchMedia` after mount rather than by CSS. The
 * obvious CSS trick -- forcing `details` content visible in a desktop media
 * query -- does not behave consistently across engines now that Chromium hides
 * it through `::details-content` and `content-visibility` rather than
 * `display`, and a disclosure that silently stops disclosing is worse than one
 * that costs a render.
 *
 * It renders closed, so the phone case is correct with no layout shift and the
 * desktop expand happens once on mount. With scripting off it stays closed and
 * still opens on click, which is the honest floor for a disclosure widget.
 */
function EarlierWork() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia('(min-width: 768px)');
    setOpen(mq.matches);
  }, []);

  return (
    <details
      className="group mb-4"
      open={open}
      onToggle={(e) => setOpen((e.currentTarget as HTMLDetailsElement).open)}
    >
      <summary className="mb-6 flex cursor-pointer list-none items-center gap-2 text-xl font-bold tracking-tight">
        {earlierWork.title}
        <span className="text-sm font-normal text-base-content/70">
          <span className="group-open:hidden">show</span>
          <span className="hidden group-open:inline">hide</span>
        </span>
      </summary>
      <div className={TERMINAL}>
        <pre data-prefix="$" className="text-info">
          <code># Before the cloud work: helpdesk to identity automation</code>
        </pre>
        {earlierWork.items.map((item, i) => (
          <Line key={i} text={item} />
        ))}
      </div>
    </details>
  );
}

export default function Projects() {
  return (
    <main className="min-h-screen bg-base-100 text-base-content">
      <div className="mx-auto max-w-4xl px-6 py-10">
        <HeaderWithTheme />

        <PageIntro
          title="Projects"
          lead="Things I have built and run, newest and most live first."
        />

        <div className={`${TERMINAL} mb-12`}>
          <pre data-prefix="$" className="text-success">
            <code>
              <Typewriter
                words={['cat projects.txt']}
                loop={1}
                typeSpeed={60}
                deleteSpeed={0}
                cursor
                cursorStyle="_"
              />
            </code>
          </pre>
        </div>

        {/* Section A.
            Order is deliberate and it is not chronological: the two things
            someone can click and use come first, then the things with a
            repository, then the work project. */}
        <h2 className="mb-6 text-xl font-bold tracking-tight">Cloud &amp; AI Projects</h2>
        <div className="mb-16 grid gap-10">
          {cloudAiProjects.map((project, index) => (
            <ProjectBlock key={project.id} project={project} index={index} />
          ))}
        </div>

        <EarlierWork />

        <div className={`${TERMINAL} mt-10`}>
          <pre data-prefix="$" className="text-info">
            <code># Also on this site</code>
          </pre>
          <pre data-prefix=">">
            <code>
              <Link href="/bikeride" className="link text-info">Bike Ride Planner</Link>
              {' '}- weather, tire pressure, and ride nutrition calculators for planning a weekend ride
            </code>
          </pre>
        </div>

        <details className="mockup-code mt-10 w-full cursor-pointer text-left font-mono [&_pre]:whitespace-pre-wrap">
          <summary className="px-4 py-2 text-sm text-info font-bold">nmap</summary>
          <pre data-prefix="$"><code>nmap travispollard.com</code></pre>
          <pre><code>Starting Nmap 7.95 ( https://nmap.org ) at 2026-09-24 23:59 CST</code></pre>
          <pre><code>Nmap scan report for travispollard.com (123.45.67.89)</code></pre>
          <pre><code>Host is up (0.021s latency).</code></pre>
          {/* 998, not 997: there is no ssh on a static CloudFront site, and the
              count is of the 1000 tcp ports nmap scans by default. */}
          <pre><code>Not shown: 998 filtered ports</code></pre>
          <pre><code>PORT     STATE SERVICE</code></pre>
          <pre><code>80/tcp   open  http</code></pre>
          <pre><code>443/tcp  open  https</code></pre>
          <pre><code>666/udp  open  doom</code></pre>
          <pre><code>19132/udp  open  minecraft</code></pre>
        </details>

      </div>
    </main>
  );
}
