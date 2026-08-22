'use client';

import HeaderWithTheme from '@/components/HeaderWithTheme';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { Typewriter } from 'react-simple-typewriter';

const featured = [
  {
    title: 'Near Mint Radar - Trading Card Price Tracker',
    links: [
      { label: 'live', url: 'https://nearmintradar.com' },
      { label: 'app repo', url: 'https://github.com/jtravisp/magictracker-app' },
      { label: 'infra repo', url: 'https://github.com/jtravisp/magictracker-infra' },
    ],
    items: [
      'Built a trading card price tracker - users watchlist cards with a target price and get an email when the price drops',
      'Next.js frontend on AWS Amplify with Google OAuth',
      'Python FastAPI backend running on Lambda behind an API Gateway HTTP API',
      'Single-table DynamoDB design, S3 price cache, and an EventBridge-scheduled daily polling job',
      'SES alert emails, Secrets Manager for credentials, and GitHub OIDC for keyless CI/CD',
      'Entire stack provisioned with Terraform',
    ],
  },
  {
    title: 'PrivatePaste - Zero-Knowledge Encrypted Vault (archived)',
    links: [],
    items: [
      'Built an encrypted text vault where the server only ever stores ciphertext and can never read a paste',
      'AES-256-GCM encryption in the browser via the Web Crypto API - the key lives in the URL fragment and is never transmitted',
      'Go standard-library HTTP server with the frontend embedded in the binary using go:embed',
      'DynamoDB with native TTL powering burn-after-read and timed paste expiry',
      'Owner tokens stored only as SHA-256 hashes; request bodies capped at 512KB at the HTTP layer',
      'Containerized on ECS Fargate behind an ALB, provisioned with Terraform using S3 remote state',
    ],
  },
  {
    title: 'The Lone Star AMPA - 36th Infantry Division Band',
    links: [
      { label: 'live', url: 'https://lonestarampa.com' },
      { label: 'repo', url: 'https://github.com/jtravisp/lonestarampa.com' },
    ],
    items: [
      'Built a study portal for the Army Musician Proficiency Assessment used by soldiers preparing for evaluation',
      'Next.js static export with an MDX content pipeline so instrument guides are authored in Markdown',
      'Per-instrument tabbed guides, rubric breakdowns, and downloadable Army regulation PDFs',
      'Styled with Tailwind CSS and deployed on Cloudflare Pages',
    ],
  },
];

const sections = [
  {
    title: 'Directory & Identity Automation',
    items: [
      'Automated employee data updates across Active Directory, Okta, and Azure using PowerShell + CSV',
      'Built Active Directory onboarding script to clone department-based templates and create new users',
      'Scripted OU membership management in Active Directory using ConnectWise Automate inventory',
      'Developed internal Okta API tools to batch manage users and group assignments',
    ],
  },
  {
    title: 'Automation & Monitoring',
    items: [
      'Created Go script to automate retrieval and download of S3 Glacier security cam footage',
      'Developed PowerShell alerting for missing BitLocker keys in Active Directory',
      'Built SharePoint storage threshold alerts using Power Automate',
    ],
  },
  {
    title: 'Imaging & Deployment',
    items: [
      'Replaced MDT with SmartDeploy and implemented PXE imaging + BitLocker key escrow in Active Directory',
      'Integrated Kandji, CXOne, and more into Okta SSO for improved user experience',
    ],
  },
  {
    title: 'Internal Tools & Documentation',
    items: [
      'Maintained IT runbooks, created README files, and published end-user guides to reduce tickets',
      'Created, tested, and documented name change process for Active Directory and other related identity services',
      'Built a custom search in ConnectWise Automate using PowerShell and Bash to dynamically update SQL-based filters for software deployment',
    ],
  },
  {
    title: 'Metrics & Optimization',
    items: [
      'Cleaned up Jira licenses, saving $20K+ annually while maintaining user access',
      'Built helpdesk dashboard in ZenDesk and automated weekly reporting to stakeholders',
    ],
  },
  {
    title: 'Portfolio & DevOps Projects',
    items: [
      'Designed and deployed personal site using Next.js, Tailwind CSS, and DaisyUI',
      'Provisioned entire infrastructure using Terraform including S3, CloudFront, Route 53, and IAM',
      'Implemented CI/CD with GitHub Actions, AWS CodePipeline, and CodeBuild',
      'Built a DynamoDB + Lambda visitor counter served via API Gateway (Python + boto3)',
    ],
  },
  {
    title: 'Linux From Scratch',
    items: [
      'Completed full Linux From Scratch (LFS) build on a Proxmox VM with a custom 6.13.4 kernel',
      'Manually compiled and configured systemd, Glibc, Bash, and other foundational packages',
      'Achieved SSH access and built a working, bootable Linux system with custom partitions',
    ],
  },
  {
    title: 'Jenkins HA on AWS',
    items: [
      'Used Packer to build Jenkins controller and agent AMIs with Ansible provisioning',
      'Provisioned infrastructure using Terraform including IAM, ASG, EFS, and ALB',
      'Stored SSH keys in AWS Parameter Store and retrieved with Python (boto3)',
      'Deployed Jenkins controller in an autoscaling group behind an ALB with a static DNS',
    ],
  },
  {
    title: 'Device Management',
    items: [
      'Implemented Kandji MDM with custom blueprints, profiles, and automated Mac provisioning',
      'Opened Apple Business account and enabled zero-touch deployment for all new Macs',
    ],
  },
];

export default function Projects() {
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
                words={["cat projects.txt"]}
                loop={1}
                typeSpeed={60}
                deleteSpeed={0}
                cursor
                cursorStyle="_"
              />
            </code>
          </pre>
        </div>

        <div className="grid gap-10 mb-10">
          {featured.map((project, index) => (
            <motion.div
              key={project.title}
              className="mockup-code w-full max-w-5xl mx-auto text-left text-lg font-mono [&_pre]:whitespace-pre-wrap"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: index * 0.1 }}
            >
              <pre data-prefix="$" className="text-success">
                <code>{`# ${project.title}`}</code>
              </pre>
              {project.items.map((item, i) => (
                <pre data-prefix=">" key={i}>
                  <code>{item}</code>
                </pre>
              ))}
              {project.links.length > 0 && (
                <pre data-prefix=">" className="text-info">
                  <code>
                    {project.links.map((link, i) => (
                      <span key={link.url}>
                        {i > 0 && ' | '}
                        <a
                          href={link.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="link"
                        >
                          {link.label}: {link.url.replace('https://', '')}
                        </a>
                      </span>
                    ))}
                  </code>
                </pre>
              )}
            </motion.div>
          ))}
        </div>

        <div className="grid gap-10">
          {sections.map((section, index) => (
            <motion.div
              key={index}
              className="mockup-code w-full max-w-5xl mx-auto text-left text-lg font-mono [&_pre]:whitespace-pre-wrap"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: index * 0.1 }}
            >
              <pre data-prefix="$" className="text-success">
                <code>{`# ${section.title}`}</code>
              </pre>
              {section.items.map((item, i) => (
                <pre data-prefix=">" key={i}>
                  <code>{item}</code>
                </pre>
              ))}
            </motion.div>
          ))}
        </div>

        <div className="mockup-code w-full max-w-5xl mx-auto text-left text-lg font-mono [&_pre]:whitespace-pre-wrap mt-10">
          <pre data-prefix="$" className="text-success">
            <code># Also on this site</code>
          </pre>
          <pre data-prefix=">">
            <code>
              <Link href="/bikeride" className="link text-info">Bike Ride Planner</Link>
              {' '}- weather, tire pressure, and ride nutrition calculators for planning a weekend ride
            </code>
          </pre>
        </div>

        <details className="mockup-code w-full max-w-5xl mx-auto text-left font-mono [&_pre]:whitespace-pre-wrap mt-10 cursor-pointer">
          <summary className="px-4 py-2 text-sm text-info font-bold">nmap</summary>
          <pre data-prefix="$"><code>nmap travispollard.com</code></pre>
          <pre><code>Starting Nmap 7.95 ( https://nmap.org ) at 2025-04-22 23:59 CST</code></pre>
          <pre><code>Nmap scan report for travispollard.com (123.45.67.89)</code></pre>
          <pre><code>Host is up (0.021s latency).</code></pre>
          <pre><code>Not shown: 997 filtered ports</code></pre>
          <pre><code>PORT     STATE SERVICE</code></pre>
          <pre><code>22/tcp   open  ssh</code></pre>
          <pre><code>80/tcp   open  http</code></pre>
          <pre><code>443/tcp  open  https</code></pre>
          <pre><code>666/udp  open  doom</code></pre>
          <pre><code>19132/udp  open  minecraft</code></pre>
        </details>

      </div>
    </main>
  );
}
