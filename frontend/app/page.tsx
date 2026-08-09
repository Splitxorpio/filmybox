import Link from "next/link";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col items-center justify-center gap-6 px-6 text-center">
      <h1 className="text-5xl font-bold tracking-tight">FilmyBox</h1>
      <p className="max-w-xl text-lg text-slate-400">
        AI-driven box office predictions for upcoming movies — a staged
        verdict at every point in a film's lifecycle, from announcement to
        release, built on real comp analysis, trained models, and audience
        sentiment.
      </p>
      <div className="flex gap-4">
        <Link
          href="/login"
          className="rounded-md bg-indigo-500 px-6 py-2.5 font-medium text-white transition hover:bg-indigo-400"
        >
          Log in
        </Link>
        <Link
          href="/about"
          className="rounded-md border border-slate-700 px-6 py-2.5 font-medium text-slate-200 transition hover:border-slate-500"
        >
          About
        </Link>
      </div>
    </main>
  );
}
