"use client";

import Link from "next/link";

export default function Techstack() {
  return (
    <section className="w-full">
      <h2 className="text-xl font-bold mb-4">Architecture</h2>
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
      <div className="mt-6">
        <Link href="/stack" className="btn btn-primary btn-sm">
          How this site is built and deployed
        </Link>
      </div>
    </section>
  );
}
