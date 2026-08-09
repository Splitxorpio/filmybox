import type { AuthOptions } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";

// Server-side only - reaches the api container via its docker-compose
// service name, same reasoning as app/page.tsx's existing health-check
// pattern (never expose this URL to the browser).
const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://api:8000";

export const authOptions: AuthOptions = {
  session: { strategy: "jwt" },
  pages: {
    signIn: "/login",
  },
  providers: [
    CredentialsProvider({
      name: "credentials",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        if (!credentials?.email || !credentials?.password) {
          return null;
        }

        const res = await fetch(`${API_INTERNAL_URL}/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: credentials.email,
            password: credentials.password,
          }),
        });

        if (!res.ok) {
          return null;
        }

        const user = await res.json();
        return { id: String(user.id), email: user.email };
      },
    }),
  ],
};
