import { NextResponse } from "next/server";

import { supabaseServer } from "@/lib/supabase-server";

export async function GET() {
  if (!supabaseServer) {
    return NextResponse.json([], { status: 200 });
  }

  const { data, error } = await supabaseServer
    .from("conclusions")
    .select("id,label,probability,confidence_band,narrative,created_at")
    .order("created_at", { ascending: false })
    .limit(12);

  if (error) {
    return NextResponse.json([], { status: 200 });
  }

  return NextResponse.json(data ?? [], { status: 200 });
}
