'use client';

import HeaderWithTheme from '@/components/HeaderWithTheme';
import { motion } from 'framer-motion';
import { Typewriter } from 'react-simple-typewriter';

const requestPath = [
  'Route 53 resolves travispollard.com and www.travispollard.com to the CloudFront distribution via alias records',
  'CloudFront terminates TLS with an ACM certificate (SNI, TLS 1.2 minimum) and redirects any HTTP request to HTTPS',
  'Cache misses fall through to the S3 static website origin holding the exported Next.js build',
  'The visitor counter calls API Gateway, which invokes a Python Lambda that increments a DynamoDB item and returns the count',
];

const pipeline = [
  'A push to the repository triggers the CodePipeline source stage',
  'CodeBuild installs dependencies with npm ci and installs Playwright browsers',
  'next build produces a fully static export of the site into frontend/out',
  'Playwright smoke tests run against the build before anything ships',
  'The build artifact is published to the S3 bucket that backs the CloudFront distribution',
];

const inventory = [
  {
    resource: 'S3',
    detail: 'Static website hosting for the exported Next.js build',
  },
  {
    resource: 'CloudFront',
    detail: 'Global CDN, TLS 1.2_2021 minimum, HTTP to HTTPS redirect, compression, PriceClass_100',
  },
  {
    resource: 'Route 53',
    detail: 'Hosted zone with alias, MX, NS, and SOA records, plus ACM validation records',
  },
  {
    resource: 'ACM',
    detail: 'TLS certificate for the apex and www names, DNS validated through Route 53',
  },
  {
    resource: 'API Gateway + Lambda + DynamoDB',
    detail: 'Visitor counter written in Python with boto3',
  },
  {
    resource: 'CodePipeline + CodeBuild',
    detail: 'Build, test, and deploy on every push, defined in buildspec.yml',
  },
  {
    resource: 'Terraform',
    detail: 'Every resource above is defined in modules: route53, s3, acm, cloudfront',
  },
];

export default function Stack() {
  return (
    <main className="min-h-screen bg-base-100 text-base-content text-lg">
      <div className="max-w-5xl mx-auto px-4 py-10">
        <HeaderWithTheme />

        <div className="mockup-code w-full max-w-5xl mx-auto text-left mb-14 text-lg font-mono [&_pre]:whitespace-pre-wrap">
          <pre data-prefix="$" className="text-info">
            <code>whoami</code>
          </pre>
          <pre data-prefix=">" className="text-warning">
            <code>travis@travispollard.com</code>
          </pre>
          <pre data-prefix=">" className="text-warning">
            <code>Cloud / DevOps Engineer</code>
          </pre>
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
          <h2 className="text-2xl font-bold mb-2">Architecture</h2>
          <a
            href="/images/travispollard.comv6.drawio.png"
            target="_blank"
            rel="noopener noreferrer"
            className="block"
          >
            <img
              src="/images/travispollard.comv6.drawio.png"
              alt="Architecture diagram: Route 53 and CloudFront serving a static Next.js site from S3, with CodePipeline and CodeBuild handling deployments and a Lambda + DynamoDB visitor counter behind API Gateway"
              className="rounded-lg shadow-lg mx-auto max-w-full h-auto"
            />
          </a>
        </motion.section>

        <motion.div
          className="mockup-code w-full max-w-5xl mx-auto text-left mb-14 text-lg font-mono [&_pre]:whitespace-pre-wrap"
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
          className="mockup-code w-full max-w-5xl mx-auto text-left mb-14 text-lg font-mono [&_pre]:whitespace-pre-wrap"
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
          <h2 className="text-2xl font-bold mb-4">Infrastructure</h2>
          <div className="overflow-x-auto">
            <table className="table table-zebra bg-base-200 rounded-box">
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
          <h2 className="text-2xl font-bold mb-4">Writeup</h2>
          <p>
            I wrote about building this stack end to end, from an empty S3 bucket to a working
            CI/CD pipeline:{' '}
            <a
              href="https://dev.to/jtravisp/from-s3-to-cicd-my-cloud-resume-challenge-journey-415o"
              target="_blank"
              rel="noopener noreferrer"
              className="link link-primary"
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
          <h2 className="text-2xl font-bold mb-4">Source</h2>
          <p>
            The Terraform configuration and the Next.js frontend for this site live in one repository:{' '}
            <a
              href="https://github.com/jtravisp/travispollard.com"
              target="_blank"
              rel="noopener noreferrer"
              className="link link-primary"
            >
              github.com/jtravisp/travispollard.com
            </a>
          </p>
        </motion.section>
      </div>
    </main>
  );
}
