const rawBackend = process.env.NEXT_PUBLIC_BACKEND_URL;
const backendTarget = rawBackend
  ? (/^https?:\/\//i.test(rawBackend.trim()) ? rawBackend.trim() : `http://${rawBackend.trim()}`).replace(/\/$/, '')
  : 'http://paloma.hidencloud.com:24666';

const isExport = process.env.NEXT_OUTPUT === 'export';

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: false,
  ...(isExport
    ? {
        output: 'export',
        images: { unoptimized: true },
      }
    : {
        async rewrites() {
          return [
            {
              source: '/api/:path*',
              destination: `${backendTarget}/api/:path*`,
            },
          ];
        },
      }),
};

export default nextConfig;
