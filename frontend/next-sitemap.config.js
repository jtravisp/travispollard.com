/** @type {import('next-sitemap').IConfig} */
module.exports = {
  siteUrl: 'https://www.travispollard.com',
  generateRobotsTxt: true, // Automatically creates robots.txt
  sitemapSize: 5000,
  changefreq: 'weekly',
  priority: 0.7,
  // /campout is a private Notion embed reached only by a class="hidden"
  // link. It was in the sitemap, which is the one place it was public.
  exclude: ['/404', '/bikeride/secret-test', '/campout', '/music/feed.xml'],
  // A drafts preview (npm run preview:music) must not write draft URLs into
  // the committed public/sitemap-0.xml, so it writes into out/ instead.
  outDir: process.env.MUSIC_INCLUDE_DRAFTS === '1' ? 'out' : 'public',
  robotsTxtOptions: {
    policies: [{ userAgent: '*', allow: '/' }],
  },
};
