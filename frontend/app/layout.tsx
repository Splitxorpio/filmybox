import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "FilmyBox",
  description: "Box office prediction dashboard",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
