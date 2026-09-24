/**
 * The three certifications, as one quiet band between the hero and the
 * project list.
 *
 * This used to open with a middot-separated technology list. It went: the
 * hero's value line and the project tags already say what the work is built
 * with, and a list of nouns above the badges was a third telling.
 *
 * The badges keep their light chip. They are vendor artwork drawn for a light
 * background, and the HashiCorp lockup in particular is near-black on
 * transparency: on the dark theme it disappears entirely. That is the one
 * place on the page a container earns itself.
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
  },
];

export default function Certifications() {
  return (
    // Left-aligned with the hero text above and the project list below.
    <section className="mb-24 border-y border-base-300 py-10" aria-label="Certifications">
      <ul className="flex flex-wrap items-center gap-x-10 gap-y-6">
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
