import { type NextRequest, NextResponse } from "next/server";

const BLOCKED_PATH_PREFIXES = ["admin", "debug", "diagnostic", "test"];

const ALLOWED_FORWARD_HEADERS = [
  "accept",
  "accept-language",
  "cache-control",
  "content-type",
  "last-event-id",
];

// Lightweight per-IP sliding window rate limiter for POST /api/investigate
const RATE_LIMIT_WINDOW_MS = 5 * 60 * 1000; // 5 minutes
const RATE_LIMIT_MAX_REQUESTS = 10; // Max 10 investigations per 5 min per IP
const investigateRateMap = new Map<string, number[]>();

function isRateLimited(clientIp: string): boolean {
  const now = Date.now();
  const timestamps = (investigateRateMap.get(clientIp) || []).filter(
    (ts) => now - ts < RATE_LIMIT_WINDOW_MS
  );
  if (timestamps.length >= RATE_LIMIT_MAX_REQUESTS) {
    investigateRateMap.set(clientIp, timestamps);
    return true;
  }
  timestamps.push(now);
  investigateRateMap.set(clientIp, timestamps);
  return false;
}

function isLocalhostUrl(rawUrl: string): boolean {
  try {
    const parsed = new URL(rawUrl);
    return (
      parsed.hostname === "localhost" ||
      parsed.hostname === "127.0.0.1" ||
      parsed.hostname === "::1"
    );
  } catch {
    return false;
  }
}

async function proxy(request: NextRequest, path: string): Promise<NextResponse> {
  // 1. Fail-closed runtime secret verification
  const apiKey = (process.env.HARIMAU_API_KEY || "").trim();
  if (!apiKey) {
    console.error(
      `[FATAL] [proxy] HARIMAU_API_KEY is missing at runtime during ${request.method} /api/${path}. Terminating frontend instance (fail-closed).`
    );
    setTimeout(() => process.exit(1), 50);
    return NextResponse.json(
      { detail: "Service misconfigured: missing HARIMAU_API_KEY" },
      { status: 503 }
    );
  }

  // 2. Block admin, debug, diagnostic, and test routes from public web proxy
  const normalizedPath = path.replace(/^\/+/, "").toLowerCase();
  const firstSegment = normalizedPath.split("/")[0] || "";
  if (BLOCKED_PATH_PREFIXES.includes(firstSegment)) {
    console.warn(
      `[proxy] Blocked forbidden path access: ${request.method} /api/${path}`
    );
    return NextResponse.json(
      { detail: "Forbidden: endpoint not accessible via web proxy" },
      { status: 403 }
    );
  }

  // 3. Per-IP rate limit on POST /api/investigate
  if (request.method === "POST" && normalizedPath === "investigate") {
    const forwardedFor = request.headers.get("x-forwarded-for");
    const clientIp = forwardedFor ? forwardedFor.split(",")[0].trim() : "unknown";
    if (isRateLimited(clientIp)) {
      console.warn(`[proxy] Rate limit exceeded for POST /api/investigate from IP ${clientIp}`);
      return NextResponse.json(
        { detail: "Too many investigation requests. Please wait a few minutes and try again." },
        { status: 429 }
      );
    }
  }

  // 4. Enforce HTTPS for non-localhost backend URLs to prevent plaintext snooping
  const backendUrl = (process.env.BACKEND_URL || "http://localhost:8080").replace(/\/+$/, "");
  if (!backendUrl.startsWith("https://") && !isLocalhostUrl(backendUrl)) {
    console.error(
      `[FATAL] [proxy] Refusing to transmit x-harimau-api-key over non-HTTPS BACKEND_URL: ${backendUrl}`
    );
    return NextResponse.json(
      { detail: "Bad Gateway: insecure upstream transport rejected" },
      { status: 502 }
    );
  }

  const url = `${backendUrl}/api/${path}${request.nextUrl.search}`;

  // 5. Strict header allowlist + inject server-side x-harimau-api-key
  const headers = new Headers();
  for (const headerName of ALLOWED_FORWARD_HEADERS) {
    const val = request.headers.get(headerName);
    if (val) {
      headers.set(headerName, val);
    }
  }
  headers.set("x-harimau-api-key", apiKey);

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

