/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:8000/api/:path*' // Assuming your FastAPI runs on port 8000
      }
    ]
  }
}

module.exports = nextConfig 