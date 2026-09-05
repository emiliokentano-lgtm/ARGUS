import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "ARGUS — War Room",
  description:
    "Selbst gehostete Echtzeit-Lageplattform. Jede Beobachtung mit Herkunft, jeder Score erklaerbar, jede Luecke sichtbar.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="de">
      <body>{children}</body>
    </html>
  );
}
