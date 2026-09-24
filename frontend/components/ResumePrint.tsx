/**
 * The resume as a printed document: what `scripts/build-resume-pdf.mjs` turns
 * into the downloadable PDF, and what a visitor gets from Ctrl+P.
 *
 * A separate rendering rather than print styles on the terminal blocks. The
 * screen version is `<pre>` lines with `$` and `>` drawn in by CSS, which an
 * ATS parser reads as prompt characters and a flat run of text with no
 * sections. This is headings and lists -- the structure the parser is looking
 * for -- and it prints black on white regardless of the theme.
 *
 * It renders nothing on screen. Both versions read `content/resume.ts`, so the
 * page and the PDF cannot say different things, and Selected Projects stays
 * screen-only because the resume itself has no such section.
 */

import { certifications, education, experience, header, skills } from '@/content/resume';

/**
 * Keeps a hyphenated word on one line. A browser may wrap after the hyphen in
 * "memory-limit", and PDF text extraction then drops it at the line end and
 * reads "memorylimit". Wrapping between words is untouched.
 */
function Unbroken({ text }: { text: string }) {
  return text.split(/(\S+-\S+)/).map((part, i) =>
    i % 2 === 1 ? (
      <span key={i} className="whitespace-nowrap">
        {part}
      </span>
    ) : (
      part
    ),
  );
}

function Heading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mt-5 mb-1.5 border-b border-black pb-0.5 text-[11pt] font-bold uppercase tracking-wide">
      {children}
    </h2>
  );
}

export default function ResumePrint() {
  return (
    // Ligatures off: Geist draws "fi" and "ff" as single glyphs, and the PDF's
    // text layer then reads "Certified" as "Certied" -- the one thing an ATS
    // parser has to get right.
    <article className="hidden bg-white text-[10pt] leading-snug text-black [font-variant-ligatures:none] print:block">
      <header>
        <h1 className="text-[20pt] font-normal">{header.name}</h1>
        <p className="mt-0.5">
          {header.contact.map((item, i) => (
            <span key={item.label}>
              {i > 0 && ' | '}
              {item.href ? <a href={item.href}>{item.label}</a> : item.label}
            </span>
          ))}
        </p>
      </header>

      <section>
        <Heading>Certifications &amp; Recognitions</Heading>
        <ul className="list-disc pl-5">
          {certifications.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>

      <section>
        <Heading>Technical Skills</Heading>
        <ul className="list-disc pl-5">
          {skills.map((row) => (
            <li key={row.label}>
              <strong>{row.label}:</strong> <Unbroken text={row.value} />
            </li>
          ))}
        </ul>
      </section>

      <section>
        <Heading>Work Experience</Heading>
        {experience.map((role) => (
          <div key={role.employer} className="mb-2.5 break-inside-avoid">
            <p className="flex justify-between gap-4">
              <span>
                <strong>{role.employer}</strong>, {role.location}
              </span>
              <strong className="shrink-0">{role.dates}</strong>
            </p>
            <p className="font-bold">{role.title}</p>
            <ul className="list-disc pl-5">
              {role.bullets.map((bullet) => (
                <li key={bullet}>
                  <Unbroken text={bullet} />
                </li>
              ))}
            </ul>
          </div>
        ))}
      </section>

      <section>
        <Heading>Education</Heading>
        {education.map((item) => (
          <p key={item}>{item}</p>
        ))}
      </section>
    </article>
  );
}
