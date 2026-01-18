// app/api/use-cases/route.ts
import { NextResponse } from "next/server"

export async function POST(req: Request) {
  try {
    const body = await req.json()

    // FastAPI läuft lokal auf 127.0.0.1:8000
    const res = await fetch("http://127.0.0.1:8000/use-cases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    })

    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch (e: any) {
    return NextResponse.json(
      { error: "use-cases route failed", detail: String(e?.message ?? e) },
      { status: 500 }
    )
  }
}
