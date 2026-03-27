const PROD_ASK_URL = process.env.AURORA_API_URL ?? "https://aurora-endpoint.onrender.com/ask";

export async function POST(request: Request) {
  const payload = (await request.json().catch(() => null)) as { question?: unknown } | null;

  if (!payload || typeof payload.question !== "string" || payload.question.trim().length === 0) {
    return Response.json(
      {
        error: "Invalid request body.",
        detail: 'Expected JSON in the shape { "question": "..." }',
      },
      { status: 400 },
    );
  }

  try {
    const upstream = await fetch(PROD_ASK_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ question: payload.question.trim() }),
      cache: "no-store",
    });

    const rawText = await upstream.text();

    try {
      const json = rawText ? JSON.parse(rawText) : {};
      return Response.json(json, { status: upstream.status });
    } catch {
      return Response.json(
        {
          error: "The upstream endpoint did not return valid JSON.",
          raw: rawText,
        },
        { status: upstream.status || 502 },
      );
    }
  } catch (error) {
    return Response.json(
      {
        error: "Unable to reach the Aurora production endpoint.",
        detail: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 502 },
    );
  }
}
