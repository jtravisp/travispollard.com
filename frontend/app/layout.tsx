import { Geist, Geist_Mono } from "next/font/google";
import Head from "next/head";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata = {
  title: 'Travis Pollard - Cloud / DevOps Engineer',
  description: 'Personal website and resume of Travis Pollard, a cloud and DevOps engineer based in Austin, TX. AWS certified, Terraform, active Secret clearance.',
  keywords: ['Travis Pollard', 'Cloud Engineer', 'DevOps Engineer', 'Platform Engineer', 'DevOps', 'AWS', 'Terraform', 'Salesforce', 'Docker', 'Next.js', 'Resume'],
  authors: [{ name: 'Travis Pollard', url: 'https://www.travispollard.com' }],
  creator: 'Travis Pollard',
  openGraph: {
    title: 'Travis Pollard - Cloud / DevOps Engineer',
    description: 'Resume of Travis Pollard, Cloud and DevOps Engineer.',
    url: 'https://www.travispollard.com',
    siteName: 'Travis Pollard Portfolio',
    type: 'website',
    images: [
      {
        url: 'https://www.travispollard.com/images/og-card.png',
        width: 1200,
        height: 630,
        alt: 'Travis Pollard - Cloud / DevOps Engineer',
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Travis Pollard - Cloud / DevOps Engineer',
    description: 'Cloud and DevOps engineer in Austin, TX. AWS certified, Terraform, CI/CD.',
    images: ['https://www.travispollard.com/images/og-card.png'],
  },
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <Head>
        <link rel="icon" href="/images/favicon.ico" sizes="any" />
        <meta name="theme-color" content="#0f172a" />
      </Head>
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        {children}
      </body>
    </html>
  );
}
