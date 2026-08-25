import { getServerSession } from "next-auth";
import Link from "next/link";
import { redirect } from "next/navigation";

import { authOptions } from "@/lib/auth";

// Server-side only - reaches the api container via its docker-compose
// service name, same reasoning as lib/auth.ts.
const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://api:8000";
const TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p";

type MovieSummary = {
  id: number;
  title: string;
  release_date: string | null;
  studio_name: string | null;
  budget_usd: number | null;
  poster_path: string | null;
};

type Verdict = {
  stage: string;
  method: string;
  verdict_bucket: string | null;
  roi_multiple_p50: number | null;
};

type MovieWithVerdict = MovieSummary & { verdict: Verdict | null };

async function getUpcomingMoviesWithVerdicts(): Promise<MovieWithVerdict[]> {
  const listRes = await fetch(`${API_INTERNAL_URL}/movies?upcoming=true&limit=50`, {
    cache: "no-store",
  });
  const { items } = (await listRes.json()) as { items: MovieSummary[] };

  const withVerdicts = await Promise.all(
    items.map(async (movie) => {
      const res = await fetch(`${API_INTERNAL_URL}/movies/${movie.id}/verdicts`, {
        cache: "no-store",
      });
      const verdicts = (await res.json()) as Verdict[];
      // Verdicts are ordered by stage rank ascending - the last gbt_v3 entry
      // is the movie's current (most advanced) stage prediction. (Was
      // hardcoded to gbt_v2 - silently stale since gbt_v3 shipped, same bug
      // class as gbt_predictor.py's METHOD staleness, found while building
      // the released-movies page.)
      const gbtVerdicts = verdicts.filter((v) => v.method === "gbt_v3");
      const current = gbtVerdicts[gbtVerdicts.length - 1] ?? null;
      return { ...movie, verdict: current };
    })
  );

  return withVerdicts;
}

const BUCKET_STYLES: Record<string, string> = {
  flop: "bg-red-950 text-red-300",
  solid: "bg-slate-800 text-slate-300",
  hit: "bg-emerald-950 text-emerald-300",
  blockbuster: "bg-indigo-950 text-indigo-300",
};

export default async function Dashboard() {
  const session = await getServerSession(authOptions);
  if (!session) {
    redirect("/login");
  }

  const movies = await getUpcomingMoviesWithVerdicts();

  return (
    <main className="mx-auto max-w-4xl px-6 py-12">
      <div className="flex items-baseline justify-between">
        <h1 className="text-2xl font-bold">Upcoming Movies</h1>
        <span className="text-sm text-slate-400">{session.user?.email}</span>
      </div>
      <p className="mt-1 text-sm text-slate-400">
        {movies.length} movies not yet released, with current predictions where available.{" "}
        <Link href="/dashboard/released" className="text-indigo-400 hover:underline">
          View released movies &rarr;
        </Link>
      </p>

      <div className="mt-8 overflow-hidden rounded-lg border border-slate-800">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-900 text-slate-400">
            <tr>
              <th className="px-4 py-3 font-medium"></th>
              <th className="px-4 py-3 font-medium">Title</th>
              <th className="px-4 py-3 font-medium">Release Date</th>
              <th className="px-4 py-3 font-medium">Studio</th>
              <th className="px-4 py-3 font-medium">Verdict</th>
              <th className="px-4 py-3 font-medium">Predicted ROI</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {movies.map((movie) => (
              <tr key={movie.id} className="transition hover:bg-slate-900/50">
                <td className="px-4 py-3">
                  {movie.poster_path ? (
                    <img
                      src={`${TMDB_IMAGE_BASE}/w92${movie.poster_path}`}
                      alt=""
                      className="h-14 w-10 rounded object-cover"
                    />
                  ) : (
                    <div className="h-14 w-10 rounded bg-slate-800" />
                  )}
                </td>
                <td className="px-4 py-3 font-medium">
                  <Link href={`/dashboard/${movie.id}`} className="hover:text-indigo-400 hover:underline">
                    {movie.title}
                  </Link>
                </td>
                <td className="px-4 py-3 text-slate-400">
                  {movie.release_date ?? "TBD"}
                </td>
                <td className="px-4 py-3 text-slate-400">
                  {movie.studio_name ?? "—"}
                </td>
                <td className="px-4 py-3">
                  {movie.verdict?.verdict_bucket ? (
                    <span
                      className={`rounded px-2 py-1 text-xs font-medium ${
                        BUCKET_STYLES[movie.verdict.verdict_bucket] ??
                        "bg-slate-800 text-slate-300"
                      }`}
                    >
                      {movie.verdict.verdict_bucket}
                    </span>
                  ) : (
                    <span className="text-xs text-slate-500">no prediction yet</span>
                  )}
                </td>
                <td className="px-4 py-3 text-slate-400">
                  {movie.verdict?.roi_multiple_p50
                    ? `${movie.verdict.roi_multiple_p50.toFixed(2)}x`
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
