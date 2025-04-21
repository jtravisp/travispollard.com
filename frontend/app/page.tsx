'use client';
import Link from "next/link";
import Techstack from "./techstack";


export default function Home() {
  return (
    <main className="min-h-screen bg-base-100 text-base-content">
      <div className="max-w-5xl mx-auto px-4 py-10">

        {/* Header */}
        <header className="flex flex-col sm:flex-row justify-between items-center mb-10">
          <h1 className="text-4xl font-extrabold text-gray-100">Travis Pollard</h1>
          <nav>
            <ul className="flex flex-wrap gap-4 text-sm font-medium text-gray-300">
              <li><Link href="/" className="link link-hover">Home</Link></li>
              <li><Link href="/resume" className="link link-hover">Resume</Link></li>
              <li><a href="https://www.linkedin.com/in/travis-pollard" target="_blank" className="link link-hover">LinkedIn</a></li>
              <li><a href="https://medium.com/@travis_17385" target="_blank" className="link link-hover">Medium</a></li>
              <li><a href="/bikeride/bikeride.html" className="link link-hover">Bike Ride</a></li>
            </ul>
          </nav>
        </header>

        {/* Intro */}
        <section className="flex flex-col gap-6 mb-16 items-center text-center">
          <p className="text-lg font-semibold text-gray-300 max-w-xl">
            I build things in the cloud
          </p>

          <div className="mockup-code w-full max-w-xl text-left">
            <pre data-prefix="$">
              <code>whoami</code>
            </pre>
            <pre data-prefix="$" className="text-warning">
              <code>travis@travispollard.com, Cloud Architect</code>
            </pre>
            <pre data-prefix="$" className="text-success">
              <code>sudo deploy --region us-east-1 --project resume-site</code>
            </pre>
          </div>

          <img
            src="/images/travis.png"
            alt="Travis Pollard"
            className="rounded-box shadow-lg max-w-[450px] h-auto"
          />
        </section>

        <section className="flex flex-col items-center gap-6 mb-16 text-center">
          <Techstack />
        </section>

        {/* Cert Badges */}
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
