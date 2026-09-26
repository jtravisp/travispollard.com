import { sectionMetadata } from '@/lib/seo';

export const metadata = sectionMetadata({
  title: 'Projects',
  description:
    'Cloud and AI projects: a multi-agent Bedrock app for Army evaluations, an Elo model that scores itself against the betting market, a serverless price tracker, and the Terraform behind this site.',
  path: '/projects/',
});

export default function ProjectsLayout({ children }: { children: React.ReactNode }) {
  return children;
}
