/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  trailingSlash: true, // <--- this is the key!
};

module.exports = nextConfig;
