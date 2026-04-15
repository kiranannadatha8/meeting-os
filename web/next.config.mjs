/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Emits a self-contained server bundle at .next/standalone — used by the
  // Docker runtime stage so the image ships only the node_modules Next needs.
  output: 'standalone',
};

export default nextConfig;
