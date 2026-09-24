import Link from 'next/link';

export default function NotFoundPage() {
    return (
      <main className="min-h-screen bg-base-100 bg-dot-grid text-base-content flex flex-col items-center justify-center px-4">
        <div className="mockup-code w-full max-w-2xl text-left text-lg font-mono [&_pre]:whitespace-pre-wrap">
          <pre data-prefix="$" className="text-error">
            <code>whoami</code>
          </pre>
          <pre data-prefix=">" className="text-warning">
            <code>travis@travispollard.com</code>
          </pre>
          <pre data-prefix="$" className="text-success">
            <code>cd /404</code>
          </pre>
          <pre data-prefix=">" className="text-warning">
            <code>no such file or directory: /404</code>
          </pre>
          <pre data-prefix=">" className="text-info">
            <code>
              Try <Link href="/" className="link">going home</Link> or checking the URL.
            </code>
          </pre>
        </div>
      </main>
    );
  }
 