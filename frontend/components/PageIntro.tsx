/**
 * The heading block every non-home page opens with.
 *
 * /projects, /resume and /stack each rolled their own: three different max
 * widths, three different top margins, and three copies of the same whoami
 * terminal repeating the role a visitor had already read in the hero. One
 * component means one set of spacing decisions, and changing the rhythm is one
 * edit rather than three that drift.
 *
 * `action` is for the one thing a page might offer at the top -- the resume's
 * PDF download. Pages without one pass nothing and get the same spacing.
 */

export default function PageIntro({
  title,
  lead,
  action,
}: {
  title: string;
  lead?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="mb-10 flex flex-wrap items-end justify-between gap-4 border-b border-base-300 pb-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">{title}</h1>
        {lead && <p className="mt-2 max-w-2xl text-base-content/70">{lead}</p>}
      </div>
      {action}
    </div>
  );
}
