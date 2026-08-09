import Link from "next/link";

export default function About() {
  return (
    <main className="mx-auto max-w-2xl px-6 py-16">
      <Link href="/" className="text-sm text-slate-400 hover:text-slate-200">
        &larr; Back
      </Link>
      <h1 className="mt-6 text-3xl font-bold">About FilmyBox</h1>
      <div className="mt-6 space-y-4 text-slate-300">
        <p>
          FilmyBox predicts a movie&apos;s box-office outcome at every stage
          of its lifecycle — announcement, teaser, trailer, pre-release, and
          post-release — updating as real signal becomes available instead
          of making one static guess.
        </p>
        <p>
          Predictions come from a gradient-boosted model trained on budget,
          cast/director/studio track record, critic scores, and audience
          sentiment pulled from trailer comments and social platforms,
          benchmarked against a comp-based heuristic baseline for every
          movie.
        </p>
        <p>
          Data is ingested from TMDb, Box Office Mojo, OMDb, Wikidata,
          YouTube, and Bluesky, feeding a pipeline that runs daily as new
          releases and reactions come in.
        </p>
      </div>
    </main>
  );
}
