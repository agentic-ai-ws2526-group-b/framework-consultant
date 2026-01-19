import { NextResponse } from "next/server"

export async function POST(req: Request) {
  try {
    const body = await req.json()

    const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8000"
    const resp = await fetch(`${backendUrl}/agent`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body), // Body 1:1 weitergeben (force_frameworks bleibt erhalten)
      cache: "no-store",
    })

    const text = await resp.text()

    return new NextResponse(text, {
      status: resp.status,
      headers: { "Content-Type": "application/json" },
    })
  } catch (e: any) {
    return NextResponse.json(
      { error: e?.message || String(e) },
      { status: 500 }
    )
  }
}
