'use client';

import HeaderWithTheme from '@/components/HeaderWithTheme';
import VisitorCounter from '@/components/VisitorCounter';
import Link from 'next/link';
import Techstack from "./techstack";

export default function Home() {
  return (
    <main className="min-h-screen bg-base-100 text-base-content">
      <div className="max-w-5xl mx-auto px-4 py-10">

        {/* Header */}
        <HeaderWithTheme />

        {/* Intro */}
        <section className="flex flex-col gap-6 mb-16 items-center text-center">
          <div className="mockup-code w-full max-w-xl text-left">
            <pre data-prefix="$">
              <code>whoami</code>
            </pre>
            <pre data-prefix=">" className="text-warning">
              <code><a href="mailto:travis@travispollard.com" className="link">travis@travispollard.com</a></code>
            </pre>
            <pre data-prefix=">" className="text-warning">
              <code>Cloud / DevOps Engineer</code>
            </pre>
          </div>

          <img
            src="/images/travis.webp"
            alt="Travis Pollard"
            width={900}
            height={900}
            className="rounded-box shadow-lg w-full max-w-[450px] h-auto"
          />
        </section>

        <div className="flex flex-wrap justify-center gap-4 mb-8">
          <Link href="/resume" className="btn btn-accent">
            View My Resume
          </Link>
          <Link href="/projects" className="btn btn-primary">
            See My Projects
          </Link>
          <a
            href="/Travis%20Pollard%20Resume.pdf"
            download
            className="btn btn-secondary"
          >
            Download Resume (PDF)
          </a>
        </div>

        {/* Writing */}
        <section className="w-full max-w-3xl mx-auto mb-16">
          <h2 className="text-xl font-bold mb-4">Writing</h2>
          <div className="flex flex-col gap-3">
            <a
              href="https://dev.to/jtravisp/from-s3-to-cicd-my-cloud-resume-challenge-journey-415o"
              target="_blank"
              rel="noopener noreferrer"
              className="card bg-base-200 hover:bg-base-300 transition-colors p-4 border-l-4 border-primary"
            >
              <span className="font-semibold">
                From S3 to CI/CD: My Cloud Resume Challenge Journey
              </span>
              <span className="text-sm opacity-70">dev.to</span>
            </a>
            <a
              href="https://medium.com/@travis_17385"
              target="_blank"
              rel="noopener noreferrer"
              className="card bg-base-200 hover:bg-base-300 transition-colors p-4 border-l-4 border-primary"
            >
              <span className="font-semibold">More posts on cloud, automation, and career change</span>
              <span className="text-sm opacity-70">Medium</span>
            </a>
          </div>
        </section>

        <section className="flex flex-col items-center gap-6 mb-16 text-center">
          <Techstack />
        </section>

        {/* Skill Badges */}
        <section className="flex flex-wrap justify-center gap-8 mb-20">
          {[
            { src: '/images/AWS%20CSA.png', alt: 'AWS Certified Solutions Architect - Associate badge' },
            { src: '/images/AWS%20Dev.png', alt: 'AWS Certified Developer - Associate badge' },
            { src: '/images/terraform.webp', alt: 'HashiCorp Certified: Terraform Associate badge' },
          ].map((badge) => (
            <img
              key={badge.src}
              src={badge.src}
              alt={badge.alt}
              className="mask mask-squircle w-[150px] h-auto shadow-md"
            />
          ))}
        </section>

        {/* Footer */}
        <footer className="footer footer-center p-6 bg-neutral text-neutral-content rounded-lg">
          <p>&copy; 2026 Travis Pollard - Austin, TX - travis@travispollard.com</p>
        </footer>

        <VisitorCounter />

      </div>

      <Link href="/campout" className="hidden">Campout</Link>

    </main>
  );
}
