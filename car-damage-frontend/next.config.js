/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    const backendUrl   = process.env.BACKEND_URL   ?? 'http://localhost:8000';
    const inferenceUrl = process.env.INFERENCE_URL ?? 'http://localhost:8001';
    return [
      // Backend REST API
      {
        source: '/api/v1/:path*',
        destination: `${backendUrl}/api/v1/:path*`,
      },
      // Inference service REST API (proxied to avoid browser CORS)
      {
        source: '/api/inference/:path*',
        destination: `${inferenceUrl}/:path*`,
      },
    ];
  },
  images: {
    remotePatterns: [
      { protocol: 'http', hostname: 'localhost', port: '9000', pathname: '/**' },
    ],
  },
};

module.exports = nextConfig;
