import type { NextConfig } from "next";

// เว็บเป็น static site ทั้งหมด (ไม่มี backend) — build แล้วได้โฟลเดอร์ out/
const nextConfig: NextConfig = {
  output: "export",
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
