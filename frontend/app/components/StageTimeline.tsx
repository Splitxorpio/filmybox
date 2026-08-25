const STAGE_ORDER = ["announcement", "teaser", "trailer", "pre_release", "post_release"];
const STAGE_LABELS: Record<string, string> = {
  announcement: "Announcement",
  teaser: "Teaser",
  trailer: "Trailer",
  pre_release: "Pre-release",
  post_release: "Post-release",
};

const BUCKET_STYLES: Record<string, string> = {
  flop: "border-red-500 bg-red-950 text-red-300",
  solid: "border-slate-500 bg-slate-800 text-slate-300",
  hit: "border-emerald-500 bg-emerald-950 text-emerald-300",
  blockbuster: "border-indigo-500 bg-indigo-950 text-indigo-300",
};

export type TimelineVerdict = {
  stage: string;
  roi_multiple_p50: number | null;
  verdict_bucket: string | null;
  actual_roi_multiple: number | null;
  actual_bucket: string | null;
};

function formatUsd(amount: number): string {
  if (amount >= 1_000_000_000) return `$${(amount / 1_000_000_000).toFixed(2)}B`;
  return `$${(amount / 1_000_000).toFixed(1)}M`;
}

export default function StageTimeline({
  verdicts,
  isReleased,
  totalWorldwide,
}: {
  verdicts: TimelineVerdict[];
  isReleased: boolean;
  totalWorldwide?: number | null;
}) {
  const byStage = new Map(verdicts.map((v) => [v.stage, v]));
  let prevRoi: number | null = null;

  return (
    <div className="mt-4">
      <div className="flex items-start">
        {STAGE_ORDER.map((stage, i) => {
          const v = byStage.get(stage);
          const reached = !!v;
          const isLast = i === STAGE_ORDER.length - 1;
          const bucket = v?.verdict_bucket ?? null;
          const dotStyle = reached
            ? (bucket ? BUCKET_STYLES[bucket] : null) ?? "border-slate-400 bg-slate-700 text-slate-200"
            : "border-slate-700 bg-slate-900 text-slate-600";

          let delta: number | null = null;
          if (reached && v!.roi_multiple_p50 !== null) {
            if (prevRoi !== null) delta = v!.roi_multiple_p50 - prevRoi;
            prevRoi = v!.roi_multiple_p50;
          }

          const showActual = isReleased && stage === "post_release" && v?.actual_bucket;

          return (
            <div key={stage} className="flex flex-1 flex-col items-center">
              <div className="flex w-full items-center">
                <div
                  className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full border-2 text-xs font-semibold ${dotStyle}`}
                  title={STAGE_LABELS[stage]}
                >
                  {v?.roi_multiple_p50 !== null && v?.roi_multiple_p50 !== undefined
                    ? `${v.roi_multiple_p50.toFixed(1)}x`
                    : "—"}
                </div>
                {!isLast && (
                  <div
                    className={`h-0.5 flex-1 ${
                      reached && byStage.get(STAGE_ORDER[i + 1]) ? "bg-slate-500" : "bg-slate-800"
                    }`}
                  />
                )}
              </div>

              <span className="mt-2 text-center text-xs font-medium text-slate-400">
                {STAGE_LABELS[stage]}
              </span>

              {reached && delta !== null && (
                <span
                  className={`mt-1 text-xs font-medium ${
                    delta > 0 ? "text-emerald-400" : delta < 0 ? "text-red-400" : "text-slate-500"
                  }`}
                >
                  {delta > 0 ? "+" : ""}
                  {delta.toFixed(2)}x
                </span>
              )}

              {reached && bucket && (
                <span className="mt-1 text-center text-xs text-slate-500">{bucket}</span>
              )}

              {showActual && (
                <span className="mt-1 text-center text-xs font-semibold text-emerald-400">
                  actual: {v!.actual_bucket} ({v!.actual_roi_multiple?.toFixed(2)}x)
                </span>
              )}
            </div>
          );
        })}
      </div>

      {isReleased && typeof totalWorldwide === "number" ? (
        <p className="mt-6 text-sm text-slate-300">
          Total worldwide box office: <span className="font-semibold text-white">{formatUsd(totalWorldwide)}</span>
        </p>
      ) : !isReleased && byStage.size > 0 ? (
        <p className="mt-6 text-sm text-slate-400">
          Expected outcome as of the latest stage:{" "}
          <span className="font-semibold text-white">
            {(() => {
              const last = STAGE_ORDER.filter((s) => byStage.has(s)).pop();
              const v = last ? byStage.get(last) : undefined;
              return v?.roi_multiple_p50 !== null && v?.roi_multiple_p50 !== undefined
                ? `${v.roi_multiple_p50.toFixed(2)}x (${v.verdict_bucket ?? "n/a"})`
                : "n/a";
            })()}
          </span>
        </p>
      ) : null}
    </div>
  );
}
