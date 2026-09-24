/**
 * The three certifications, as one quiet band between the hero and the
 * project list.
 *
 * This used to open with a middot-separated technology list. It went: the
 * hero's value line and the project tags already say what the work is built
 * with, and a list of nouns above the badges was a third telling.
 *
 * Each badge sits on a card built from the theme's own surfaces -- a subtle
 * dark card on the dark theme, a pale one on light -- rather than the white
 * chip they used to have, which on the dark theme read as three bright
 * blocks.
 *
 * Dropping the chip exposes the one badge drawn for a light background: the
 * HashiCorp lockup's "Terraform" wordmark is near-black on transparency and
 * vanishes on a dark card. `invertOnDark` flips it on the dark theme only
 * (see globals.css): invert turns the wordmark white, and the 180-degree hue
 * rotation puts the purple mark back to purple. HashiCorp publishes white-
 * wordmark lockups for dark backgrounds, so this is the brand's own reverse
 * treatment rather than a recolour.
 */

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
    invertOnDark: true,
  },
];

export default function Certifications() {
  return (
    // Left-aligned with the hero text above and the project list below.
    <section className="mb-32" aria-label="Certifications">
      <ul className="grid gap-4 sm:grid-cols-3">
        {CERTIFICATIONS.map((cert) => (
          <li
            key={cert.src}
            className="flex items-center gap-4 rounded-lg border border-base-300 bg-base-200/60 p-4"
          >
            <img
              src={cert.src}
              alt={cert.alt}
              width={56}
              height={56}
              className={`h-14 w-14 shrink-0 object-contain ${
                'invertOnDark' in cert && cert.invertOnDark ? 'invert-on-dark' : ''
              }`}
            />
            <span className="text-sm leading-snug text-base-content/70">{cert.label}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
