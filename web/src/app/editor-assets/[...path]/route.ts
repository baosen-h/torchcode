import { readFile } from "node:fs/promises";
import { extname, join } from "node:path";

export const runtime = "nodejs";

const CONTENT_TYPES: Record<string, string> = {
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
  ".ttf": "font/ttf",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".svg": "image/svg+xml",
};

export async function GET(_request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const contentType = CONTENT_TYPES[extname(path.at(-1) || "")];
  if (path[0] !== "vs" || !contentType || path.some((part) => !/^[\w.-]+$/.test(part) || part === "." || part === "..")) {
    return new Response("Not found", { status: 404 });
  }
  try {
    const content = await readFile(join(process.cwd(), "node_modules", "monaco-editor", "min", ...path));
    return new Response(new Uint8Array(content), { headers: {
      "Content-Type": contentType,
      "Cache-Control": "public, max-age=86400",
      "X-Content-Type-Options": "nosniff",
    } });
  } catch {
    return new Response("Not found", { status: 404 });
  }
}
