'use client';

import HeaderWithTheme from '@/components/HeaderWithTheme';
import PageIntro from '@/components/PageIntro';
import ResumePrint from '@/components/ResumePrint';
import { cloudAiProjects, visibleSummary, visibleTags } from '@/content/projects';
import { certifications, education, experience, skills } from '@/content/resume';
import { site } from '@/content/site';
import { motion } from 'framer-motion';
import Link from 'next/link';
import { Typewriter } from 'react-simple-typewriter';

const TERMINAL = 'mockup-code w-full text-left text-base font-mono [&_pre]:whitespace-pre-wrap';

function Section({
  title,
  delay,
  children,
}: {
  title: string;
  delay: number;
  children: React.ReactNode;
}) {
  return (
    <motion.div
      className={`${TERMINAL} mb-10`}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay }}
    >
      <pre data-prefix="$" className="text-info">
        <code># {title}</code>
      </pre>
      {children}
    </motion.div>
  );
}

/** The projects the resume names, from the same objects /projects renders. */
const RESUME_PROJECT_IDS = ['ncoer-writer', 'cfb-forecast', 'near-mint-radar', 'privatepaste'];

export default function Resume() {
  const resumeProjects = RESUME_PROJECT_IDS.map((id) => cloudAiProjects.find((p) => p.id === id)!);

  return (
    <main className="min-h-screen bg-base-100 bg-dot-grid text-base-content print:min-h-0">
      <ResumePrint />

      <div className="mx-auto max-w-4xl px-6 py-10 print:hidden">
        <HeaderWithTheme />

        <PageIntro
          title="Resume"
          lead={`${site.role} in ${site.location}. Active Secret clearance.`}
          action={
            <a href={site.resumePdf} download className="btn btn-primary btn-sm">
              Download PDF
            </a>
          }
        />

        <div className={`${TERMINAL} mb-10`}>
          <pre data-prefix="$" className="text-info">
            <code>whoami</code>
          </pre>
          <pre data-prefix=">">
            <code>
              <a href={`mailto:${site.email}`} className="link">
                {site.email}
              </a>
            </code>
          </pre>
          <pre data-prefix=">">
            <code>
              <a href={site.github} target="_blank" rel="noopener noreferrer" className="link">
                github.com/jtravisp
              </a>
              {'   '}
              <a href={site.linkedin} target="_blank" rel="noopener noreferrer" className="link">
                linkedin.com/in/travis-pollard
              </a>
            </code>
          </pre>
          <pre data-prefix="$" className="text-success">
            <code>
              <Typewriter
                words={['cat resume.txt']}
                loop={1}
                typeSpeed={60}
                deleteSpeed={0}
                cursor
                cursorStyle="_"
              />
            </code>
          </pre>
        </div>

        <Section title="Certifications & Recognitions" delay={0.1}>
          {certifications.map((item) => (
            <pre data-prefix=">" key={item}>
              <code>{item}</code>
            </pre>
          ))}
        </Section>

        <Section title="Technical Skills" delay={0.15}>
          {skills.map((row) => (
            <pre data-prefix=">" key={row.label}>
              <code>
                <strong>{row.label}:</strong> {row.value}
              </code>
            </pre>
          ))}
        </Section>

        <Section title="Selected Projects" delay={0.2}>
          {resumeProjects.map((project) => (
            <pre data-prefix=">" key={project.id}>
              <code>
                {project.links.length > 0 ? (
                  <a
                    href={project.links[0].url}
                    target={project.links[0].url.startsWith('http') ? '_blank' : undefined}
                    rel="noopener noreferrer"
                    className="link"
                  >
                    {project.cardTitle}
                  </a>
                ) : (
                  project.cardTitle
                )}
                {visibleSummary(project) && ` - ${visibleSummary(project)}`}
                {visibleTags(project).length > 0 && `  ${visibleTags(project).join(' · ')}`}
              </code>
            </pre>
          ))}
        </Section>

        <Section title="Work Experience" delay={0.25}>
          {experience.map((role) => (
            <div key={role.employer}>
              <pre data-prefix=">">
                <code>
                  <strong>{role.employer}</strong>, {role.location} - {role.title} ({role.dates})
                </code>
              </pre>
              {role.bullets.map((bullet, i) => (
                <pre data-prefix=" " className="sub-bullet" key={i}>
                  <code>{'  - '}{bullet}</code>
                </pre>
              ))}
            </div>
          ))}
        </Section>

        <Section title="Education" delay={0.3}>
          {education.map((item) => (
            <pre data-prefix=">" key={item}>
              <code>{item}</code>
            </pre>
          ))}
        </Section>
      </div>

      <Link href="/campout" className="hidden" aria-hidden="true">
        Hidden Campout
      </Link>
    </main>
  );
}
