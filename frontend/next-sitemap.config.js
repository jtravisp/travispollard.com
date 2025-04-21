/** @type {import('next-sitemap').IConfig} */
module.exports = {
  siteUrl: 'https://www.travispollard.com',
  generateRobotsTxt: true, // Automatically creates robots.txt
  sitemapSize: 5000,
  changefreq: 'weekly',
  priority: 0.7,
  exclude: ['/404', '/bikeride/secret-test'],
  robotsTxtOptions: {
    policies: [{ userAgent: '*', allow: '/' }],
  },
};
