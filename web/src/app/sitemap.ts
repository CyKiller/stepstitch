import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/links";

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: SITE_URL, changeFrequency: "weekly", priority: 1 },
    { url: `${SITE_URL}/dashboard`, changeFrequency: "monthly", priority: 0.9 },
    { url: `${SITE_URL}/security`, changeFrequency: "monthly", priority: 0.8 },
    { url: `${SITE_URL}/self-host`, changeFrequency: "monthly", priority: 0.8 },
    { url: `${SITE_URL}/who-its-for`, changeFrequency: "monthly", priority: 0.8 },
  ];
}
