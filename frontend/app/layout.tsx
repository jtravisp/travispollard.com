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
  title: 'Travis Pollard – Cloud Architect',
  description: 'Personal website and resume of Travis Pollard, a cloud architect and technical lead based in Austin, TX. AWS certified, Terraform, Salesforce, DevOps.',
  keywords: ['Travis Pollard', 'Cloud Architect', 'Technical Lead', 'DevOps', 'AWS', 'Terraform', 'Salesforce', 'Docker', 'Next.js', 'Resume'],
  authors: [{ name: 'Travis Pollard', url: 'https://www.travispollard.com' }],
  creator: 'Travis Pollard',
  openGraph: {
    title: 'Travis Pollard – Cloud Architect',
    description: 'Resume of Travis Pollard, Cloud Architect and Technical Lead.',
    url: 'https://www.travispollard.com',
    siteName: 'Travis Pollard Portfolio',
    type: 'website',
    images: [
      {
        url: 'https://www.travispollard.com/images/travis.png',
        width: 1200,
        height: 630,
        alt: 'Travis Pollard Headshot',
      },
    ],
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
