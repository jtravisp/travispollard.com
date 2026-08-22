'use client';

import HeaderWithTheme from '@/components/HeaderWithTheme';
import { motion } from 'framer-motion';
import Link from 'next/link';
import { Typewriter } from 'react-simple-typewriter';

export default function Resume() {
  return (
    <main className="min-h-screen bg-base-100 text-base-content text-xl">
      <div className="max-w-5xl mx-auto px-4 py-10">
        {/* Header */}
        <HeaderWithTheme />

        <div className="w-full">
          {/* Terminal-style intro */}
          <div className="mockup-code w-full max-w-5xl mx-auto text-left mb-14 text-lg">
            <pre data-prefix="$">
              <code className="text-info">whoami</code>
            </pre>
            <pre data-prefix=">" className="text-warning">
              <code><a href="mailto:travis@travispollard.com" className="link">travis@travispollard.com</a></code>
            </pre>
            <pre data-prefix=">" className="text-warning">
              <code>Cloud / DevOps Engineer</code>
            </pre>
            <pre data-prefix=">" className="text-warning">
              <code>Austin, TX - Active Secret clearance</code>
            </pre>
            <pre data-prefix=">" className="text-warning">
              <code>
                <a href="https://github.com/jtravisp" target="_blank" rel="noopener noreferrer" className="link">github.com/jtravisp</a>
              </code>
            </pre>
            <pre data-prefix="$" className="text-success">
              <code>
                <Typewriter
                  words={['cat resume.txt']}
                  loop={1}
                  typeSpeed={60}
                  deleteSpeed={0}
                  cursor
                  cursorStyle="_"
                />
              </code>
            </pre>
          </div>

          {/* Resume download */}
          <div className="flex justify-center mb-14">
            <a
              href="/Travis%20Pollard%20Resume.pdf"
              download
              className="btn btn-accent"
            >
              Download Resume (PDF)
            </a>
          </div>

          {/* Certifications Section */}
          <motion.div
            className="mockup-code w-full max-w-5xl mx-auto text-left mb-14 text-lg font-mono [&_pre]:whitespace-pre-wrap"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.2 }}
          >
            <pre data-prefix="$" className="text-info">
              <code># 🛡 Certifications & Recognitions</code>
            </pre>
            {[
              "AWS Certified Developer - Associate",
              "AWS Certified Solutions Architect - Associate",
              "HashiCorp Certified: Terraform Associate",
              "Secret Level Clearance, Active",
              "CompTIA Security+, Network+, A+",
              "edX Harvard CS50x Computer Science Certificate and CS50p Python Certificate",
            ].map((item, idx) => (
              <pre data-prefix=">" key={idx}><code>{item}</code></pre>
            ))}
          </motion.div>

          {/* Technical Skills Section */}
          <motion.div
            className="mockup-code w-full max-w-5xl mx-auto text-left mb-14 text-lg font-mono [&_pre]:whitespace-pre-wrap"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.3 }}
          >
            <pre data-prefix="$" className="text-info">
              <code># 💻 Technical Skills</code>
            </pre>
            <pre data-prefix=">">
              <code><strong>Programming:</strong> Python, Go, TypeScript, Powershell, SQL</code>
            </pre>
            <pre data-prefix=">">
              <code><strong>Cloud & Infrastructure:</strong> AWS, Azure, Terraform, Docker, ECS/Fargate, Lambda, DynamoDB, CI/CD</code>
            </pre>
            <pre data-prefix=">">
              <code><strong>Platforms & Tools:</strong> Salesforce (Admin, Development), Git, Jira, Okta, Active Directory / Entra ID, M365, Google Workspace, Connectwise Automate, Kandji, Netsuite</code>
            </pre>
            <pre data-prefix=">">
              <code><strong>Other:</strong> Agile Project Management, Troubleshooting, Process Automation, Technical Documentation, Stakeholder Communication</code>
            </pre>
          </motion.div>

          {/* Selected Projects Section */}
          <motion.div
            className="mockup-code w-full max-w-5xl mx-auto text-left mb-14 text-lg font-mono [&_pre]:whitespace-pre-wrap"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.35 }}
          >
            <pre data-prefix="$" className="text-info">
              <code># Selected Projects</code>
            </pre>
            <pre data-prefix=">">
              <code>
                <a href="https://nearmintradar.com" target="_blank" rel="noopener noreferrer" className="link">Near Mint Radar</a>
                {' '}- trading card price tracker: Next.js on Amplify, FastAPI on Lambda, DynamoDB, EventBridge polling, SES alerts, all Terraform
              </code>
            </pre>
            <pre data-prefix=">">
              <code>
                PrivatePaste - zero-knowledge encrypted vault: Go + Web Crypto (AES-256-GCM), DynamoDB TTL, ECS Fargate behind an ALB, Terraform
              </code>
            </pre>
            <pre data-prefix=">">
              <code>
                <a href="https://lonestarampa.com" target="_blank" rel="noopener noreferrer" className="link">The Lone Star AMPA</a>
                {' '}- Army musician assessment study portal: Next.js static export with MDX content pipeline, deployed on Cloudflare Pages
              </code>
            </pre>
            <pre data-prefix=">">
              <code>
                <a href="/projects" className="link">travispollard.com</a>
                {' '}- this site: Next.js on S3 + CloudFront, Terraform-provisioned, CodePipeline/CodeBuild CI/CD, Lambda + DynamoDB visitor counter
              </code>
            </pre>
          </motion.div>

          {/* Work Experience Section */}
          <motion.div
            className="mockup-code w-full max-w-5xl mx-auto text-left mb-14 text-lg font-mono [&_pre]:whitespace-pre-wrap"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.4 }}
          >
            <pre data-prefix="$" className="text-info">
              <code># 🧑‍💼 Work Experience</code>
            </pre>
            <pre data-prefix=">">
              <code>Nuvitek, Washington, DC - Platform Engineer, US Department of Labor (2024-Present)</code>
            </pre>
            <pre data-prefix=" "><code>  • Expanded scope to serve as de facto PM, BA, and QA lead for multiple federal Salesforce apps following team reduction</code></pre>
            <pre data-prefix=" "><code>  • Architected and containerized an internal LMS (Moodle) using a custom Docker image deployed to AWS ECS with Terraform</code></pre>
            <pre data-prefix=" "><code>  • Led technical planning and execution of Salesforce Experience Cloud migration from .com to .gov domains</code></pre>
            <pre data-prefix=" "><code>  • Authored Jira epics, stories, and acceptance criteria across multiple concurrent projects</code></pre>
            <pre data-prefix=" "><code>  • Produced technical documentation and user guides for federal reporting applications</code></pre>
            <pre data-prefix=" "><code>  • Performed Salesforce administration: user access audits, custom reports, bug troubleshooting, dev QA</code></pre>
            <pre data-prefix=">">
              <code>United States Gold Bureau, Austin, TX - IT Support and Systems Specialist (2023-2024)</code>
            </pre>
            <pre data-prefix=" "><code>  • Supported 200+ end users, implemented Apple MDM (Kandji), trained new IT staff, administered M365/Entra, automated processes with PowerShell, Go, and Bash</code></pre>
            <pre data-prefix=">">
              <code>Texas Army National Guard, 36th Infantry Division Band, Austin, TX - Sergeant First Class, Music Performance Team Leader (2007-Present)</code>
            </pre>
            <pre data-prefix=" "><code>  • Supervise a platoon of 12 soldiers and lead performance team of 18 soldiers</code></pre>
            <pre data-prefix=">">
              <code>Brentwood Christian School, Austin, TX - Band Director / Fine Arts Chair / Theater Manager (2006-2023)</code>
            </pre>
          </motion.div>

          {/* Education Section */}
          <motion.div
            className="mockup-code w-full max-w-5xl mx-auto text-left text-lg font-mono [&_pre]:whitespace-pre-wrap"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.5 }}
          >
            <pre data-prefix="$" className="text-info">
              <code># 🎓 Education</code>
            </pre>
            <pre data-prefix=">">
              <code>The University of Texas at Austin - Master's in Music and Human Learning</code>
            </pre>
            <pre data-prefix=">">
              <code>Tennessee Technological University - Bachelor's in Music Education</code>
            </pre>
          </motion.div>
        </div>
      </div>

      <Link href="/campout" className="hidden" aria-hidden="true">Hidden Campout</Link>

    </main>
  );
}
