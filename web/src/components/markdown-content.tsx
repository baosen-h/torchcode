"use client";

import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";

const MAX_IMAGE_URL_LENGTH = 1_500_000;
const IMAGE_DATA_URL = /^data:image\/(?:png|jpeg|webp|gif);base64,[A-Za-z0-9+/=]+$/;

export function MarkdownContent({ children, preserveHeading = false }: { children: string; preserveHeading?: boolean }) {
  return <div className={`markdown-body ${preserveHeading ? "preserve-heading" : ""}`}>
    <ReactMarkdown urlTransform={(url, key, node) => {
      if (key === "src" && node.tagName === "img" && url.length <= MAX_IMAGE_URL_LENGTH && IMAGE_DATA_URL.test(url)) return url;
      return defaultUrlTransform(url);
    }} remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>{children}</ReactMarkdown>
  </div>;
}
