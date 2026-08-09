"use client";

import { signIn } from "next-auth/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

export default function Login() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);

    const res = await signIn("credentials", {
      email,
      password,
      redirect: false,
    });

    setSubmitting(false);

    if (res?.error) {
      setError("Invalid email or password.");
      return;
    }

    router.push("/dashboard");
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-6">
      <h1 className="text-2xl font-bold">Log in</h1>
      <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
        <input
          type="email"
          required
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="rounded-md border border-slate-700 bg-slate-900 px-4 py-2 outline-none focus:border-indigo-500"
        />
        <input
          type="password"
          required
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="rounded-md border border-slate-700 bg-slate-900 px-4 py-2 outline-none focus:border-indigo-500"
        />
        {error && <p className="text-sm text-red-400">{error}</p>}
        <button
          type="submit"
          disabled={submitting}
          className="rounded-md bg-indigo-500 px-4 py-2 font-medium text-white transition hover:bg-indigo-400 disabled:opacity-50"
        >
          {submitting ? "Logging in..." : "Log in"}
        </button>
      </form>
      <p className="mt-4 text-sm text-slate-400">
        No account?{" "}
        <Link href="/register" className="text-indigo-400 hover:underline">
          Register
        </Link>
      </p>
    </main>
  );
}
