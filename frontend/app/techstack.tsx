"use client";

export default function Techstack() {
    return (
      <>
        <div className="bg-base-200 p-6 rounded-box shadow-lg w-full max-w-2xl mx-auto mb-2">
          <h2 className="text-center text-xl font-bold mb-4">Technology Stack</h2>
          <ul className="flex flex-col gap-3">
            <li className="flex items-start gap-2">
              <span>💻</span>
              <span>
                Built with <strong>Next.js</strong> and styled using <strong>Tailwind CSS</strong> and <strong>daisyUI</strong>
              </span>
            </li>
            <li className="flex items-start gap-2">
              <span>🌐</span>
              <span>
                Deployed as a static site on <strong>Amazon S3</strong> with global delivery via <strong>CloudFront CDN</strong>
              </span>
            </li>
            <li className="flex items-start gap-2">
              <span>🗺️</span>
              <span>
                Domain and DNS managed through <strong>Route 53</strong>
              </span>
            </li>
            <li className="flex items-start gap-2">
              <span>🔗</span>
              <span>
                CI/CD powered by <strong>AWS CodePipeline</strong> and <strong>CodeBuild</strong> for zero-touch deployments
              </span>
            </li>
            <li className="flex items-start gap-2">
              <span>📦</span>
              <span>
                Infrastructure provisioned in <strong>AWS</strong> with <strong>Terraform</strong>
              </span>
            </li>
          </ul>
        </div>

        <section className="my-12 text-center">
        <h2 className="text-xl font-bold mb-4">Architecture Diagram</h2>
        <img
          src="/images/travispollard.comv6.drawio.png"
          alt="Cloud infrastructure diagram for travispollard.com"
          className="rounded-lg shadow-lg mx-auto max-w-full h-auto"
        />
      </section>
    </>
    );
  }
  