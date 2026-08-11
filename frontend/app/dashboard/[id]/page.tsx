import { getServerSession } from "next-auth";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { authOptions } from "@/lib/auth";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://api:8000";

type MovieDetail = {
  id: number;
  title: string;
  release_date: string | null;
  budget_usd: number | null;
  studio: { name: string } | null;
};

type Verdict = {
  stage: string;
  method: string;
  computed_at: string;
  comp_count: number;
  roi_multiple_p25: number | null;
  roi_multiple_p50: number | null;
  roi_multiple_p75: number | null;
  verdict_bucket: string | null;
  actual_roi_multiple: number | null;
  actual_bucket: string | null;
};

type SentimentSnapshot = {
  source: string;
  stage: string;
  snapshot_date: string;
  sentiment_score: number | null;
  volume: number | null;
  avg_engagement_score: number | null;
};

const STAGE_ORDER = ["announcement", "teaser", "trailer", "pre_release", "post_release"];
const METHOD_LABELS: Record<string, string> = {
  comp_heuristic_v1: "Comp Heuristic",
  gbt_v1: "GBT v1",
  gbt_v2: "GBT v2",
};

const BUCKET_STYLES: Record<string, string> = {
  flop: "bg-red-950 text-red-300",
  solid: "bg-slate-800 text-slate-300",
  hit: "bg-emerald-950 text-emerald-300",
  blockbuster: "bg-indigo-950 text-indigo-300",
};

async function getMovieDetail(id: string): Promise<MovieDetail | null> {
  const res = await fetch(`${API_INTERNAL_URL}/movies/${id}`, { cache: "no-store" });
  if (res.status === 404) return null;
  return res.json();
}

async function getVerdicts(id: string): Promise<Verdict[]> {
  const res = await fetch(`${API_INTERNAL_URL}/movies/${id}/verdicts`, { cache: "no-store" });
  return res.json();
}

async function getSentiment(id: string): Promise<SentimentSnapshot[]> {
  const res = await fetch(`${API_INTERNAL_URL}/movies/${id}/sentiment`, { cache: "no-store" });
  return res.json();
}

export default async function MovieTimeline({ params }: { params: { id: string } }) {
  const session = await getServerSession(authOptions);
  if (!session) {
    redirect("/login");
  }

  const [movie, verdicts, sentiment] = await Promise.all([
    getMovieDetail(params.id),
    getVerdicts(params.id),
    getSentiment(params.id),
  ]);

  if (!movie) {
    notFound();
  }

  // Group verdicts by stage (in lifecycle order), each stage showing every
  // method that has a row for it - this is the "timeline" the stage_scan.py/
  // train_model.py design already produces per movie, just never surfaced
  // in the UI before now. Each stage's row is frozen once the movie moves
  // past it; only the current stage keeps getting refreshed in place.
  const stagesPresent = STAGE_ORDER.filter((stage) => verdicts.some((v) => v.stage === stage));

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <Link href="/dashboard" className="text-sm text-slate-400 hover:text-slate-200">
        &larr; Back to dashboard
      </Link>

      <div className="mt-4 flex items-baseline justify-between">
        <h1 className="text-2xl font-bold">{movie.title}</h1>
        <span className="text-sm text-slate-400">{movie.release_date ?? "TBD"}</span>
      </div>
      <p className="mt-1 text-sm text-slate-400">
        {movie.studio?.name ?? "Unknown studio"}
        {movie.budget_usd ? ` · $${(movie.budget_usd / 1_000_000).toFixed(0)}M budget` : " · budget unknown"}
      </p>

      <h2 className="mt-10 text-lg font-semibold">Prediction Timeline</h2>
      {stagesPresent.length === 0 ? (
        <p className="mt-2 text-sm text-slate-500">No predictions yet for this movie.</p>
      ) : (
        <div className="mt-4 space-y-6">
          {stagesPresent.map((stage) => {
            const stageVerdicts = verdicts.filter((v) => v.stage === stage);
            return (
              <div key={stage} className="rounded-lg border border-slate-800 p-4">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
                  {stage.replace("_", " ")}
                </h3>
                <div className="mt-3 space-y-2">
                  {stageVerdicts.map((v) => (
                    <div
                      key={v.method}
                      className="flex items-center justify-between text-sm"
                    >
                      <span className="text-slate-300">{METHOD_LABELS[v.method] ?? v.method}</span>
                      <span className="text-xs text-slate-500">
                        {v.roi_multiple_p25?.toFixed(2)}x – {v.roi_multiple_p75?.toFixed(2)}x
                      </span>
                      {v.verdict_bucket ? (
                        <span
                          className={`rounded px-2 py-0.5 text-xs font-medium ${
                            BUCKET_STYLES[v.verdict_bucket] ?? "bg-slate-800 text-slate-300"
                          }`}
                        >
                          {v.verdict_bucket} ({v.roi_multiple_p50?.toFixed(2)}x)
                        </span>
                      ) : (
                        <span className="text-xs text-slate-500">no prediction</span>
                      )}
                      {v.actual_bucket && (
                        <span className="text-xs text-emerald-400">
                          actual: {v.actual_bucket} ({v.actual_roi_multiple?.toFixed(2)}x)
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <h2 className="mt-10 text-lg font-semibold">Sentiment</h2>
      {sentiment.length === 0 ? (
        <p className="mt-2 text-sm text-slate-500">No sentiment data yet for this movie.</p>
      ) : (
        <div className="mt-4 overflow-hidden rounded-lg border border-slate-800">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-900 text-slate-400">
              <tr>
                <th className="px-4 py-2 font-medium">Source</th>
                <th className="px-4 py-2 font-medium">Stage</th>
                <th className="px-4 py-2 font-medium">Volume</th>
                <th className="px-4 py-2 font-medium">Sentiment</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {sentiment.map((s) => (
                <tr key={`${s.source}-${s.stage}`}>
                  <td className="px-4 py-2">{s.source}</td>
                  <td className="px-4 py-2 text-slate-400">{s.stage.replace("_", " ")}</td>
                  <td className="px-4 py-2 text-slate-400">{s.volume ?? "—"}</td>
                  <td className="px-4 py-2 text-slate-400">
                    {s.sentiment_score !== null ? s.sentiment_score.toFixed(2) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
