import type { Metadata } from "next";
import "./globals.css";
import { LiveProvider } from "@/lib/hooks";
import { AuthProvider } from "@/components/AuthProvider";

export const metadata: Metadata = {
  title: "Logs the Attacker Can't Erase",
  description: "Tamper-evident security logging dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          <LiveProvider>{children}</LiveProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
