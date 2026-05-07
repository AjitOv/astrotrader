import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "ASTROTRADE",
  description: "Time Intelligence Engine",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body className="font-mono antialiased" suppressHydrationWarning>
        {children}
      </body>
    </html>
  );
}
