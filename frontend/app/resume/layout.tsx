import { sectionMetadata } from '@/lib/seo';

export const metadata = sectionMetadata({
  title: 'Resume',
  description:
    'Resume of Travis Pollard, Platform Engineer in Austin, TX. AWS Solutions Architect and Developer Associate, HashiCorp Terraform Associate, active Secret clearance.',
  path: '/resume/',
});

export default function ResumeLayout({ children }: { children: React.ReactNode }) {
  return children;
}
