/**
 * The technology strip and the three certifications.
 *
 * Plain text separated by middots, not chips. Eight bordered pills is eight
 * rectangles competing with the three project cards below them for the same
 * attention, and none of it is a link -- it is a list of nouns, so it is set
 * as one.
 *
 * The certification badges keep their light chip. They are vendor artwork drawn
 * for a light background, and the HashiCorp lockup in particular is near-black
 * on transparency: on the dark theme it disappears entirely. That is the one
 * place on the page a container earns itself.
 */

import { Fragment } from 'react';

const TECHNOLOGIES = [
  'AWS',
  'Terraform',
  'Go',
  'Python',
  'Bedrock',
  'GitHub Actions',
  'Next.js',
  'Docker',
];

const CERTIFICATIONS = [
  {
    src: '/images/AWS%20CSA.png',
    alt: 'AWS Certified Solutions Architect - Associate',
    label: 'AWS Certified Solutions Architect – Associate',
  },
  {
    src: '/images/AWS%20Dev.png',
    alt: 'AWS Certified Developer - Associate',
    label: 'AWS Certified Developer – Associate',
  },
  {
    src: '/images/terraform.webp',
    alt: 'HashiCorp Certified: Terraform Associate',
    label: 'HashiCorp Terraform Associate',
  },
];

export default function TechBand() {
  return (
    <section className="mb-24 border-y border-base-300 py-10">
      {/* Left-aligned with the hero text above it and the project list below:
          a centred band between two left edges was the one thing on the page
          lining up with neither. Each name is nowrap so a phone breaks the
          line between technologies, never inside "GitHub Actions". */}
      <p className="text-sm leading-loose text-base-content/70">
        {/* The space between spans is the only break opportunity; without it
            the nowrap spans fuse into one unbreakable run that overflows. The
            middot trails its name, so a wrapped line can end on one but never
            start with one. */}
        {TECHNOLOGIES.map((tech, i) => (
          <Fragment key={tech}>
            {i > 0 && ' '}
            <span className="whitespace-nowrap">
              {tech}
              {i < TECHNOLOGIES.length - 1 && (
                <span aria-hidden="true" className="ml-2 mr-1 text-base-content/25">
                  &middot;
                </span>
              )}
            </span>
          </Fragment>
        ))}
      </p>

      <ul className="mt-8 flex flex-wrap items-center gap-x-10 gap-y-6">
        {CERTIFICATIONS.map((cert) => (
          <li key={cert.src} className="flex items-center gap-3">
            <span className="flex h-16 w-16 shrink-0 items-center justify-center rounded-box bg-white p-2">
              <img
                src={cert.src}
                alt={cert.alt}
                width={56}
                height={56}
                className="max-h-full w-auto object-contain"
              />
            </span>
            <span className="max-w-[11rem] text-sm leading-snug text-base-content/70">
              {cert.label}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
