import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Allow opening the dev server from other devices on the home network.
  allowedDevOrigins: ["192.168.1.80", "localhost"],
};

export default nextConfig;
