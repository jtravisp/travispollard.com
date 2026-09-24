export const metadata = {
  title: 'Stack',
  description:
    'How travispollard.com is built and deployed: Next.js static export on S3 and CloudFront, provisioned with Terraform, gated by GitHub Actions and shipped by CodePipeline.',
  alternates: { canonical: '/stack/' },
};

export default function StackLayout({ children }: { children: React.ReactNode }) {
  return children;
}
