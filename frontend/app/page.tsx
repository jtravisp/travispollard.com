'use client';

import HeaderWithTheme from '@/components/HeaderWithTheme';
import Link from 'next/link';
import { Typewriter } from 'react-simple-typewriter';
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
              <code>Cloud Architect</code>
            </pre>
            <pre data-prefix="$" className="text-success">
              <code>
              <Typewriter
                  words={['sudo ./deploy.sh --region us-east-1 --project resume-site']}
                  loop={1}
                  typeSpeed={60}
                  deleteSpeed={0}
                  cursor
                  cursorStyle="_"
                />
              </code>
            </pre>
          </div>

          <img
            src="/images/travis.png"
            alt="Travis Pollard"
            className="rounded-box shadow-lg max-w-[450px] h-auto"
          />
        </section>

        <div className="flex justify-center mb-8">
          <Link href="/resume" className="btn btn-accent">
            View My Resume
          </Link>
        </div>

        <section className="flex flex-col items-center gap-6 mb-16 text-center">
          <Techstack />
        </section>

        {/* Skill Badges */}
        <section className="flex flex-wrap justify-center gap-8 mb-20">
          {["awsCSA.png", "CompTIA_Security.png", "terraform.webp"].map((img) => (
            <img
              key={img}
              src={`/images/${img}`}
              alt={img}
              className="mask mask-squircle w-[150px] h-auto shadow-md"
            />
          ))}
        </section>

        {/* Footer */}
        <footer className="footer p-6 bg-neutral text-neutral-content rounded-lg justify-center">
          <p>&copy; 2025 Travis Pollard — Austin, TX — travis@travispollard.com</p>
        </footer>

      </div>
    </main>
  );
}
