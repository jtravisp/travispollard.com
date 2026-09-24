'use client';

import HeaderWithTheme from '@/components/HeaderWithTheme';
import { cloudAiProjects, earlierWork, type Project } from '@/content/projects';
import { site } from '@/content/site';
import { motion } from 'framer-motion';
import Link from 'next/link';
import { Typewriter } from 'react-simple-typewriter';

const TERMINAL =
  'mockup-code w-full max-w-5xl mx-auto text-left text-lg font-mono [&_pre]:whitespace-pre-wrap';

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
      <pre data-prefix="$" className="text-success">
        <code>{`# ${project.title}`}</code>
      </pre>
      {project.items.map((item, i) => (
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

export default function Projects() {
  return (
    <main className="min-h-screen bg-base-100 text-base-content text-lg">
      <div className="max-w-5xl mx-auto px-4 py-10">
        <HeaderWithTheme />

        <div className={`${TERMINAL} mb-14`}>
          <pre data-prefix="$" className="text-info">
            <code>whoami</code>
          </pre>
          <pre data-prefix=">" className="text-warning">
            <code>{site.email}</code>
          </pre>
          <pre data-prefix=">" className="text-warning">
            <code>{site.role}</code>
          </pre>
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
        <h2 className="mb-6 text-2xl font-bold">Cloud &amp; AI Projects</h2>
        <div className="mb-16 grid gap-10">
          {cloudAiProjects.map((project, index) => (
            <ProjectBlock key={project.id} project={project} index={index} />
          ))}
        </div>

        {/* Section B.
            Six terminal blocks used to cover identity, monitoring, imaging,
            device management, internal tools and metrics, above the cloud work
            for part of the page's life. One block now, and below. */}
        <h2 className="mb-6 text-2xl font-bold">{earlierWork.title}</h2>
        <motion.div
          className={TERMINAL}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
        >
          <pre data-prefix="$" className="text-success">
            <code># Before the cloud work: helpdesk to identity automation</code>
          </pre>
          {earlierWork.items.map((item, i) => (
            <Line key={i} text={item} />
          ))}
        </motion.div>

        <div className={`${TERMINAL} mt-10`}>
          <pre data-prefix="$" className="text-success">
            <code># Also on this site</code>
          </pre>
          <pre data-prefix=">">
            <code>
              <Link href="/bikeride" className="link text-info">Bike Ride Planner</Link>
              {' '}- weather, tire pressure, and ride nutrition calculators for planning a weekend ride
            </code>
          </pre>
        </div>

        <details className="mockup-code w-full max-w-5xl mx-auto text-left font-mono [&_pre]:whitespace-pre-wrap mt-10 cursor-pointer">
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
