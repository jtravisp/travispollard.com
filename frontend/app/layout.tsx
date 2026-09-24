import { Geist, Geist_Mono } from "next/font/google";
import { site } from "@/content/site";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const TITLE = `${site.name} - ${site.role}`;
const DESCRIPTION =
  'Platform Engineer in Austin, TX. I build and operate AWS infrastructure and AI-powered apps: Terraform, serverless, Go, Python. AWS certified, active Secret clearance.';

export const metadata = {
  // Without this, a relative image or canonical in any metadata below resolves
  // against localhost during the build and ships that way.
  metadataBase: new URL(site.url),
  title: {
    default: TITLE,
    // Sub-pages set their own; they used to inherit this one verbatim, so every
    // route in the sitemap carried an identical <title>.
    template: `%s - ${site.name}`,
  },
  description: DESCRIPTION,
  keywords: ['Travis Pollard', 'Platform Engineer', 'Cloud Engineer', 'DevOps Engineer', 'AWS', 'Terraform', 'Bedrock', 'Serverless', 'Go', 'Python', 'Resume'],
  authors: [{ name: site.name, url: site.url }],
  creator: site.name,
  alternates: {
    canonical: '/',
  },
  openGraph: {
    title: TITLE,
    description: DESCRIPTION,
    url: site.url,
    siteName: `${site.name} Portfolio`,
    locale: 'en_US',
    type: 'website',
    images: [
      {
        url: '/images/og-card.png',
        width: 1200,
        height: 630,
        alt: TITLE,
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: TITLE,
    description: DESCRIPTION,
    images: ['/images/og-card.png'],
  },
};

/**
 * `themeColor` belongs here and nowhere else.
 *
 * It used to live in a `<Head>` from `next/head`, rendered inside this layout.
 * That component is Pages Router only -- in the App Router it is inert, and the
 * proof is that `out/index.html` shipped without the meta tag at all. The
 * favicon beside it looked like it worked, but only because `app/favicon.ico`
 * exists and Next's file convention emits the link independently.
 */
export const viewport = {
  themeColor: '#0f172a',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        {children}
      </body>
    </html>
  );
}
