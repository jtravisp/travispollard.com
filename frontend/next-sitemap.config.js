/** @type {import('next-sitemap').IConfig} */
module.exports = {
  siteUrl: 'https://www.travispollard.com',
  generateRobotsTxt: true, // Automatically creates robots.txt
  sitemapSize: 5000,
  changefreq: 'weekly',
  priority: 0.7,
  // /campout is a private Notion embed reached only by a class="hidden"
  // link. It was in the sitemap, which is the one place it was public.
  exclude: ['/404', '/bikeride/secret-test', '/campout'],
  robotsTxtOptions: {
    policies: [{ userAgent: '*', allow: '/' }],
  },
};
