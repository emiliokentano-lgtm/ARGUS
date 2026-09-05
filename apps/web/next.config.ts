import type { NextConfig } from "next";

/**
 * ARGUS — War Room.
 *
 * Bewusst duenn. Zwei Dinge stehen hier, und beide aus einem Grund:
 *
 * `transpilePackages` — @argus/ui-kit wird als TypeScript-Quelle eingebunden,
 * nicht als gebautes Paket. Das ist im Monorepo die einfachere Kette (kein
 * Build-Schritt zwischen Aenderung und Vorschau), verlangt aber, dass Next
 * das Paket selbst uebersetzt.
 *
 * `typedRoutes` — ein Tippfehler in einem Link soll beim Typecheck auffallen
 * und nicht als 404 beim Nutzer.
 */
const nextConfig: NextConfig = {
  transpilePackages: ["@argus/ui-kit"],
  typedRoutes: true,
  // Der Build bricht bei Typ- oder Lint-Fehlern ab. Das ist der Standard und
  // steht hier trotzdem: die beiden Schalter, die ihn abstellen, sind die
  // haeufigste Art, wie ein Monorepo seine Typpruefung im Deployment verliert.
  typescript: { ignoreBuildErrors: false },
  eslint: { ignoreDuringBuilds: false },
};

export default nextConfig;
