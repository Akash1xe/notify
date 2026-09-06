import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Notify — Lecture to PDF",
  description: "Prepare YouTube lectures locally for visual PDF notes.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
