import { getServerSession } from "next-auth";
import Link from "next/link";
import { redirect } from "next/navigation";

import { authOptions } from "@/lib/auth";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://api:8000";
const TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p";
const PAGE_SIZE = 25;

type MovieSummary = {
  id: number;
  title: string;
  release_date: string | null;
  studio_name: string | null;
  budget_usd: number | null;
  poster_path: string | null;
};

type MovieListResponse = {
  total: number;
  limit: number;
  offset: number;
  items: MovieSummary[];
};

type Verdict = {
  stage: string;
  method: string;
  verdict_bucket: string | null;
  roi_multiple_p50: number | null;
  actual_bucket: string | null;
  actual_roi_multiple: number | null;
};

type MovieWithVerdict = MovieSummary & { verdict: Verdict | null };

async function getReleasedMovies(page: number, search: string): Promise<MovieListResponse> {
  const offset = (page - 1) * PAGE_SIZE;
  const params = new URLSearchParams({
    released_only: "true",
    limit: String(PAGE_SIZE),
    offset: String(offset),
  });
  if (search) params.set("search", search);

  const res = await fetch(`${API_INTERNAL_URL}/movies?${params.toString()}`, { cache: "no-store" });
  return res.json();
}

async function withVerdicts(items: MovieSummary[]): Promise<MovieWithVerdict[]> {
  return Promise.all(
    items.map(async (movie) => {
      const res = await fetch(`${API_INTERNAL_URL}/movies/${movie.id}/verdicts`, { cache: "no-store" });
      const verdicts = (await res.json()) as Verdict[];
      // Same pattern as the upcoming dashboard: verdicts are ordered by
      // stage rank ascending, so the last gbt_v3 entry is the movie's final
      // (post_release) prediction - the one directly comparable to the
      // actual outcome, which is the whole point of this page.
      const gbtVerdicts = verdicts.filter((v) => v.method === "gbt_v3");
      const current = gbtVerdicts[gbtVerdicts.length - 1] ?? null;
      return { ...movie, verdict: current };
    })
  );
}

const BUCKET_STYLES: Record<string, string> = {
  flop: "bg-red-950 text-red-300",
  solid: "bg-slate-800 text-slate-300",
  hit: "bg-emerald-950 text-emerald-300",
  blockbuster: "bg-indigo-950 text-indigo-300",
};

function BucketBadge({ bucket }: { bucket: string | null }) {
  if (!bucket) return <span className="text-xs text-slate-500">—</span>;
  return (
    <span className={`rounded px-2 py-1 text-xs font-medium ${BUCKET_STYLES[bucket] ?? "bg-slate-800 text-slate-300"}`}>
      {bucket}
    </span>
  );
}

export default async function ReleasedMovies({
  searchParams,
}: {
  searchParams: { page?: string; search?: string };
}) {
  const session = await getServerSession(authOptions);
  if (!session) {
    redirect("/login");
  }

  const page = Math.max(1, parseInt(searchParams.page ?? "1", 10) || 1);
  const search = searchParams.search ?? "";

  const { total, items } = await getReleasedMovies(page, search);
  const movies = await withVerdicts(items);
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const pageLink = (p: number) => {
    const params = new URLSearchParams();
    if (search) params.set("search", search);
    params.set("page", String(p));
    return `/dashboard/released?${params.toString()}`;
  };

  return (
    <main className="mx-auto max-w-4xl px-6 py-12">
      <div className="flex items-baseline justify-between">
        <h1 className="text-2xl font-bold">Released Movies</h1>
        <span className="text-sm text-slate-400">{session.user?.email}</span>
      </div>
      <p className="mt-1 text-sm text-slate-400">
        {total.toLocaleString()} released movies — predicted vs. actual outcome.{" "}
        <Link href="/dashboard" className="text-indigo-400 hover:underline">
          &larr; Upcoming movies
        </Link>
      </p>

      <form className="mt-6 flex gap-2" action="/dashboard/released">
        <input
          type="text"
          name="search"
          defaultValue={search}
          placeholder="Search by title..."
          className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-500"
        />
        <button
          type="submit"
          className="rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
        >
          Search
        </button>
      </form>

      <div className="mt-6 overflow-hidden rounded-lg border border-slate-800">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-900 text-slate-400">
            <tr>
              <th className="px-4 py-3 font-medium"></th>
              <th className="px-4 py-3 font-medium">Title</th>
              <th className="px-4 py-3 font-medium">Release Date</th>
              <th className="px-4 py-3 font-medium">Studio</th>
              <th className="px-4 py-3 font-medium">Predicted</th>
              <th className="px-4 py-3 font-medium">Actual</th>
              <th className="px-4 py-3 font-medium">Correct?</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {movies.map((movie) => {
              const predicted = movie.verdict?.verdict_bucket ?? null;
              const actual = movie.verdict?.actual_bucket ?? null;
              const isCorrect = predicted !== null && actual !== null && predicted === actual;
              return (
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
                  <td className="px-4 py-3 text-slate-400">{movie.release_date ?? "—"}</td>
                  <td className="px-4 py-3 text-slate-400">{movie.studio_name ?? "—"}</td>
                  <td className="px-4 py-3">
                    <BucketBadge bucket={predicted} />
                  </td>
                  <td className="px-4 py-3">
                    <BucketBadge bucket={actual} />
                  </td>
                  <td className="px-4 py-3">
                    {predicted === null || actual === null ? (
                      <span className="text-xs text-slate-500">—</span>
                    ) : isCorrect ? (
                      <span className="text-emerald-400">✓</span>
                    ) : (
                      <span className="text-red-400">✗</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="mt-6 flex items-center justify-between text-sm text-slate-400">
        <span>
          Page {page} of {totalPages.toLocaleString()}
        </span>
        <div className="flex gap-4">
          {page > 1 && (
            <Link href={pageLink(page - 1)} className="text-indigo-400 hover:underline">
              &larr; Previous
            </Link>
          )}
          {page < totalPages && (
            <Link href={pageLink(page + 1)} className="text-indigo-400 hover:underline">
              Next &rarr;
            </Link>
          )}
        </div>
      </div>
    </main>
  );
}
