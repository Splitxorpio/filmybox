async function getApiHealth() {
  // Server-side (this component runs in the frontend container during SSR),
  // so it must reach the api container via its docker-compose service name,
  // not the browser-facing NEXT_PUBLIC_API_URL (localhost:8000).
  const apiUrl = process.env.API_INTERNAL_URL ?? "http://api:8000";
  try {
    const res = await fetch(`${apiUrl}/health`, { cache: "no-store" });
    return await res.json();
  } catch (err) {
    return { api: "unreachable", error: String(err) };
  }
}

export default async function Home() {
  const health = await getApiHealth();

  return (
    <main style={{ fontFamily: "sans-serif", padding: "2rem" }}>
      <h1>FilmyBox</h1>
      <p>Box office prediction dashboard — scaffold running.</p>
      <h2>API health</h2>
      <pre>{JSON.stringify(health, null, 2)}</pre>
    </main>
  );
}
