'use client';

import HeaderWithTheme from '@/components/HeaderWithTheme';
import PageIntro from '@/components/PageIntro';
import { motion } from 'framer-motion';
import { Typewriter } from 'react-simple-typewriter';

const requestPath = [
  'Route 53 resolves travispollard.com and www.travispollard.com to the CloudFront distribution via alias records',
  'CloudFront terminates TLS with an ACM certificate (SNI, TLS 1.2 minimum) and redirects any HTTP request to HTTPS',
  'Cache misses on the default behavior fall through to the S3 static website origin holding the exported Next.js build',
  'Requests under /cfb/data/* go to a second origin instead: the football pipeline bucket, reached through an Origin Access Control rather than a public website endpoint',
  'The visitor counter calls API Gateway, which invokes a Python Lambda that increments a DynamoDB item and returns the count',
];

// Two systems, and the page used to describe only the second one.
//
// CodePipeline is the deploy and it runs after the merge decision. The Actions
// job runs before it, which is the only place a check can stop a bad merge
// rather than a bad deploy -- so leaving it out made the interesting half of
// the story invisible.
const pipeline = [
  'A pull request runs the GitHub Actions gate: typecheck, lint, a full static export, and the Playwright suite on Chromium and Firefox',
  'That job pins TZ=UTC and the same Node version CodeBuild uses, because a gate running a different environment from the deploy has a gap in exactly the shape of the bug it is meant to catch',
  'A merge to main fires a webhook that starts CodePipeline within seconds',
  'CodeBuild installs with npm ci, builds the static export into frontend/out, and runs the same Playwright suite again',
  'The build artifact is deployed to the S3 bucket that backs the CloudFront distribution',
  'A final stage invalidates the distribution, so the change is visible without waiting out a TTL',
];

const inventory = [
  {
    resource: 'S3',
    detail: 'Static website hosting for the exported Next.js build, read by CloudFront as a custom origin',
  },
  {
    resource: 'CloudFront',
    detail: 'Global CDN, TLS 1.2_2021 minimum, HTTP to HTTPS redirect, compression, PriceClass_100, plus a second origin for /cfb/data/*',
  },
  {
    resource: 'Route 53',
    detail: 'Hosted zone with alias, MX, NS, and SOA records, plus ACM validation records',
  },
  {
    resource: 'ACM',
    detail: 'TLS certificate for the apex and www names, DNS validated through Route 53, in us-east-1 because CloudFront requires it',
  },
  {
    resource: 'API Gateway + Lambda + DynamoDB',
    detail: 'Visitor counter written in Python with boto3',
  },
  {
    resource: 'GitHub Actions',
    detail: 'Pre-merge gate: typecheck, lint, static export, and Playwright on two browsers, pinned to UTC',
  },
  {
    resource: 'CodePipeline + CodeBuild',
    detail: 'Post-merge deploy: build and test per buildspec.yml, S3 deploy, then a CloudFront invalidation',
  },
  {
    resource: 'SSM Parameter Store',
    detail: 'The seam between this stack and the football pipeline: distribution id and ARN, so neither reads the other Terraform state',
  },
  {
    resource: 'Terraform',
    detail:
      'S3, CloudFront, Route 53 and ACM are the modules s3, cloudfront, route53 and acm; the SSM parameters sit beside them. The visitor counter and the CodePipeline were built outside Terraform',
  },
];

export default function Stack() {
  return (
    <main className="min-h-screen bg-base-100 text-base-content">
      <div className="mx-auto max-w-4xl px-6 py-10">
        <HeaderWithTheme />

        <PageIntro
          title="Stack"
          lead="How this site is built, tested and deployed, and what the Terraform actually declares."
        />

        <div className="mockup-code mb-12 w-full text-left text-base font-mono [&_pre]:whitespace-pre-wrap">
          <pre data-prefix="$" className="text-success">
            <code>
              <Typewriter
                words={['terraform show travispollard.com']}
                loop={1}
                typeSpeed={60}
                deleteSpeed={0}
                cursor
                cursorStyle="_"
              />
            </code>
          </pre>
        </div>

        <motion.section
          className="mb-14"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
        >
          <h2 className="mb-3 text-xl font-bold tracking-tight">Architecture</h2>
          <a
            href="/images/travispollard.comv6.drawio.png"
            target="_blank"
            rel="noopener noreferrer"
            className="block"
          >
            <img
              src="/images/travispollard.comv6.drawio.png"
              width={1101}
              height={726}
              alt="Architecture diagram: Route 53 and CloudFront serving a static Next.js site from S3, with CodePipeline and CodeBuild handling deployments and a Lambda + DynamoDB visitor counter behind API Gateway"
              className="rounded-lg shadow-lg mx-auto max-w-full h-auto"
            />
          </a>
        </motion.section>

        <motion.div
          className="mockup-code mb-12 w-full text-left text-base font-mono [&_pre]:whitespace-pre-wrap"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.1 }}
        >
          <pre data-prefix="$" className="text-info">
            <code># Request path</code>
          </pre>
          {requestPath.map((step, i) => (
            <pre data-prefix=">" key={i}>
              <code>{step}</code>
            </pre>
          ))}
        </motion.div>

        <motion.div
          className="mockup-code mb-12 w-full text-left text-base font-mono [&_pre]:whitespace-pre-wrap"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.2 }}
        >
          <pre data-prefix="$" className="text-info">
            <code># Commit to production</code>
          </pre>
          {pipeline.map((step, i) => (
            <pre data-prefix=">" key={i}>
              <code>{`${i + 1}. ${step}`}</code>
            </pre>
          ))}
        </motion.div>

        <motion.section
          className="mb-14"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.3 }}
        >
          <h2 className="mb-4 text-xl font-bold tracking-tight">Infrastructure</h2>
          <div className="overflow-x-auto">
            <table className="table table-zebra bg-base-200 rounded-box [&_thead]:text-base-content/80">
              <thead>
                <tr>
                  <th>Resource</th>
                  <th>Configuration</th>
                </tr>
              </thead>
              <tbody>
                {inventory.map((row) => (
                  <tr key={row.resource}>
                    <td className="font-mono whitespace-nowrap align-top">{row.resource}</td>
                    <td>{row.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </motion.section>

        <motion.section
          className="mb-14"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.35 }}
        >
          <h2 className="mb-4 text-xl font-bold tracking-tight">Writeup</h2>
          <p>
            I wrote about building this stack end to end, from an empty S3 bucket to a working
            CI/CD pipeline:{' '}
            <a
              href="https://dev.to/jtravisp/from-s3-to-cicd-my-cloud-resume-challenge-journey-415o"
              target="_blank"
              rel="noopener noreferrer"
              className="link font-medium"
            >
              From S3 to CI/CD: My Cloud Resume Challenge Journey
            </a>
          </p>
        </motion.section>

        <motion.section
          className="mb-14"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.4 }}
        >
          <h2 className="mb-4 text-xl font-bold tracking-tight">Source</h2>
          <p>
            The Terraform configuration and the Next.js frontend for this site live in one repository:{' '}
            <a
              href="https://github.com/jtravisp/travispollard.com"
              target="_blank"
              rel="noopener noreferrer"
              className="link font-medium"
            >
              github.com/jtravisp/travispollard.com
            </a>
          </p>
        </motion.section>
      </div>
    </main>
  );
}
