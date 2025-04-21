"use client";

export default function Techstack() {
    return (
      <div className="bg-base-200 p-6 rounded-box shadow-lg w-full max-w-2xl mx-auto mb-16">
        <h2 className="text-center text-xl font-bold mb-4">Technology Stack</h2>
        <ul className="flex flex-col gap-3">
          <li className="flex items-start gap-2">
            <span>💻</span>
            <span>
              Built with <strong>Next.js</strong> and styled using <strong>Tailwind CSS + daisyUI</strong>
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span>🌐</span>
            <span>
              Static site hosted via <strong>Amazon S3</strong> with <strong>CloudFront CDN</strong>
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span>🗺️</span>
            <span>
              DNS managed in <strong>Route 53</strong> with a custom domain
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span>🔗</span>
            <span>
              CI/CD pipeline powered by <strong>CodePipeline</strong> and <strong>CodeBuild</strong>
            </span>
          </li>
          <li className="flex items-start gap-2">
            <span>📦</span>
            <span>
              Provisioned with <strong>Terraform</strong> for full Infrastructure as Code
            </span>
          </li>
        </ul>
      </div>
    );
  }
  