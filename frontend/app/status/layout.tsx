export const metadata = {
  title: 'Status',
  description:
    'Live uptime, latency and TLS certificate checks for the projects Travis Pollard runs, refreshed every ten minutes by a serverless checker.',
  alternates: { canonical: '/status/' },
};

export default function StatusLayout({ children }: { children: React.ReactNode }) {
  return children;
}
