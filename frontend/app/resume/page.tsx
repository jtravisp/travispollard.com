export default function Resume() {
    return (
      <main className="max-w-4xl mx-auto px-4 py-12 text-gray-900">
        <h1 className="text-3xl font-bold mb-4">Travis Pollard</h1>
        <p className="mb-2">Full Legal Name: John Travis Pollard</p>
        <p className="mb-6">travis@travispollard.com ❖ (512) 567-5859 ❖ Austin, TX</p>
  
        <div className="mb-8">
          <a
            href="https://www.linkedin.com/in/travis-pollard"
            target="_blank"
            className="inline-block"
          >
            <img
              src="/images/viewlinkedin.png"
              alt="LinkedIn"
              width={200}
              className="hover:opacity-80 transition"
            />
          </a>
        </div>
  
        <section className="mb-10">
          <h2 className="text-2xl font-semibold mb-2">Work Experience</h2>
  
          <div className="mb-4">
            <h3 className="text-xl font-bold">Brentwood Christian School (2006 - Present)</h3>
            <h4 className="text-lg">Band Director, Fine Arts Chair, Theater Manager</h4>
            <p>Austin, TX</p>
          </div>
  
          <div>
            <h3 className="text-xl font-bold">
              Texas Army National Guard - 36th Infantry Division Band (2007 - Present)
            </h3>
            <h4 className="text-lg">
              Staff Sergeant, Squad Leader, Music Ensemble Leader, Musician
            </h4>
            <p>Austin, TX</p>
          </div>
        </section>
  
        <section className="mb-10">
          <h2 className="text-2xl font-semibold mb-2">Education</h2>
  
          <div className="mb-4">
            <h3 className="text-xl font-bold">Tennessee Technological University, 2003</h3>
            <h4 className="text-lg">Bachelor's in Music Education</h4>
            <p>Cookeville, TN</p>
          </div>
  
          <div>
            <h3 className="text-xl font-bold">The University of Texas at Austin, 2007</h3>
            <h4 className="text-lg">Master's in Music and Human Learning</h4>
            <p>Austin, TX</p>
          </div>
        </section>
  
        <section className="mb-10">
          <h2 className="text-2xl font-semibold mb-2">Recognitions & Certifications</h2>
          <ul className="list-disc list-inside space-y-2">
            <li>
              CompTIA Secure Infrastructure Specialist:
              <ul className="list-disc ml-6 space-y-1">
                <li>
                  <a
                    href="https://www.credly.com/badges/04be4503-2179-4f9a-b6a1-d1dad9c41974"
                    target="_blank"
                    className="text-blue-600 underline"
                  >
                    CompTIA Security+
                  </a>
                </li>
                <li>
                  <a
                    href="https://www.credly.com/badges/0ffd84af-6515-428a-916b-5dc7dda9f315"
                    target="_blank"
                    className="text-blue-600 underline"
                  >
                    CompTIA Network+
                  </a>
                </li>
                <li>
                  <a
                    href="https://www.credly.com/badges/dfe828c5-d9de-4d3a-b642-3d5e7ac143c3"
                    target="_blank"
                    className="text-blue-600 underline"
                  >
                    CompTIA A+
                  </a>
                </li>
              </ul>
            </li>
            <li>edX Harvard CS50x Computer Science Certificate</li>
            <li>edX Harvard CS50p Python Certificate</li>
            <li>Google Data Analytics Professional Certificate (Coursera)</li>
            <li>Amazon Web Services (AWS) Fundamentals (Coursera)</li>
            <li>Secret level clearance, active</li>
            <li>US Army School of Music Peer Mentor Award, ALC, 2022</li>
            <li>Texas Christian Schools Association, Teacher of the Year, 2015</li>
          </ul>
        </section>
  
        <section className="mb-10">
          <h2 className="text-2xl font-semibold mb-2">Skills & Interests</h2>
          <h3 className="text-lg font-medium">Skills</h3>
          <p className="mb-2">
            Networking, Windows and Linux, Google Suite, HTML/CSS, JavaScript, Python, SQL, Teaching, Live Sound Design, Theater Lighting, Team Leadership
          </p>
          <h3 className="text-lg font-medium">Interests</h3>
          <p>
            Ethical Hacking, Reading, Chess, Building PCs, Saxophone, Flute, Piano, Triathlons
          </p>
        </section>
  
        <footer className="text-center text-sm text-gray-500 border-t pt-4">
          <p>&copy; Travis Pollard. All rights reserved.</p>
        </footer>
      </main>
    );
  }
  