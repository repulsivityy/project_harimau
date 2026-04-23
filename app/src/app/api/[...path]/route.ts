import { type NextRequest, NextResponse } from "next/server";

// Read at request time from Cloud Run env var — not baked at build time
const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8080";

async function proxy(request: NextRequest, path: string): Promise<NextResponse> {
  const url = `${BACKEND_URL}/api/${path}${request.nextUrl.search}`;

  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (key !== "host") headers.set(key, value);
  });

  const init: RequestInit = { method: request.method, headers };

  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.arrayBuffer();
  }

  let upstream: Response;
  try {
    upstream = await fetch(url, init);
  } catch (err) {
    console.error(`[proxy] fetch failed: ${request.method} ${url}`, err);
    return new NextResponse("Bad Gateway", { status: 502 });
  }

  if (!upstream.ok) {
    console.error(`[proxy] upstream error: ${request.method} ${url} → ${upstream.status}`);
  }

  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: upstream.headers,
  });
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return proxy(request, path.join("/"));
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return proxy(request, path.join("/"));
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return proxy(request, path.join("/"));
}
