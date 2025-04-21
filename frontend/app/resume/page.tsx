'use client';

import HeaderWithTheme from '@/components/HeaderWithTheme';
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
              <code>Cloud Architect</code>
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

        {/* Certifications Section */}
        <div className="mockup-code w-full max-w-5xl mx-auto text-left mb-14 text-lg font-mono">
          <pre data-prefix="$" className="text-info">
            <code># 🛡 Certifications & Recognitions</code>
          </pre>
          {[
            "AWS Certified Solutions Architect - Associate",
            "Secret Level Clearance (Active)",
            "CompTIA Security+, Network+, A+",
            "edX CS50x & CS50p Certificates",
            "Google Data Analytics Professional Certificate",
            "TAPPS Fine Arts Teacher of the Year (2023)",
            "Peer Mentor Award, Army School of Music (2022)",
            "Finley R. Hamilton Outstanding Military Musician Award (2024)"
          ].map((item, idx) => (
            <pre data-prefix=">" key={idx}><code>{item}</code></pre>
          ))}
        </div>

        {/* Technical Skills Section */}
        <div className="mockup-code w-full max-w-5xl mx-auto text-left mb-14 text-lg font-mono">
          <pre data-prefix="$" className="text-info">
            <code># 💻 Technical Skills</code>
          </pre>
          <pre data-prefix=">">
            <code>Python, Go, Powershell, SQL, HTML, CSS, JavaScript</code>
          </pre>
          <pre data-prefix=">">
            <code>AWS, Azure, Terraform, AD, Entra, Google, M365, Okta</code>
          </pre>
          <pre data-prefix=">">
            <code>Linux, Windows, MacOS</code>
          </pre>
          <pre data-prefix=">">
            <code>Proxmox, Docker, Apache, Wireguard, Pi-hole, NAS</code>
          </pre>
        </div>

        {/* Work Experience Section */}
        <div className="mockup-code w-full max-w-5xl mx-auto text-left mb-14 text-lg font-mono">
          <pre data-prefix="$" className="text-info">
            <code># 🧑‍💼 Work Experience</code>
          </pre>
          <pre data-prefix=">">
            <code>Nuvitek, Washington, DC - IT Support Trainer (2024-Present)</code>
          </pre>
          <pre data-prefix=">">
            <code>US Gold Bureau, Leander, TX - IT Support and Systems Specialist (2023-2024)</code>
          </pre>
          <pre data-prefix=">">
            <code>TX Army National Guard, Austin, TX - SSG, Squad Leader (2007-Present)</code>
          </pre>
          <pre data-prefix=">">
            <code>Brentwood Christian School - Band Director / Fine Arts Chair / Theater Manager (2006-2023)</code>
          </pre>
        </div>

        {/* Education Section */}
        <div className="mockup-code w-full max-w-5xl mx-auto text-left text-lg font-mono">
          <pre data-prefix="$" className="text-info">
            <code># 🎓 Education</code>
          </pre>
          <pre data-prefix=">">
            <code>The University of Texas at Austin - M.M. in Music and Human Learning</code>
          </pre>
          <pre data-prefix=">">
            <code>Tennessee Technological University - B.M. in Music Education</code>
          </pre>
        </div>

        </div>

      </div>
    </main>
  );
}
