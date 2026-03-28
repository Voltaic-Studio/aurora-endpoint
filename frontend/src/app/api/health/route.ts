const PROD_API_URL = process.env.AURORA_API_URL ?? "https://aurora-endpoint.onrender.com/ask";
const PROD_HEALTH_URL = new URL("/health", PROD_API_URL).toString();

export async function GET() {
  try {
    const upstream = await fetch(PROD_HEALTH_URL, {
      method: "GET",
      cache: "no-store",
    });

    const rawText = await upstream.text();

    try {
      const json = rawText ? JSON.parse(rawText) : {};
      return Response.json(json, { status: upstream.status });
    } catch {
      return Response.json(
        {
          error: "The upstream health endpoint did not return valid JSON.",
          raw: rawText,
        },
        { status: upstream.status || 502 },
      );
    }
  } catch (error) {
    return Response.json(
      {
        error: "Unable to reach the Aurora production health endpoint.",
        detail: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 502 },
    );
  }
}
