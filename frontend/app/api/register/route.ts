import { NextRequest, NextResponse } from "next/server";

// Thin proxy to the backend's /auth/register - keeps API_INTERNAL_URL
// server-side only, same reasoning as lib/auth.ts and the existing
// health-check pattern in app/page.tsx.
const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://api:8000";

export async function POST(req: NextRequest) {
  const body = await req.json();

  const res = await fetch(`${API_INTERNAL_URL}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
