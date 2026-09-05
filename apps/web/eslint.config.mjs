// ARGUS War Room — ESLint.
//
// Erbt die Wurzelkonfiguration (unbenutzte Variablen, eqeqeq, kein console)
// und ergaenzt sie um zwei Dinge, die nur im Browser gelten: die
// JSX-Globals und die Next-Regeln.
//
// Die Next-Regeln sind kein Schmuck. Sie fangen genau die Fehler ab, die im
// Build nicht auffallen und erst beim Nutzer wirken: ein <img> statt
// <Image>, ein <a href> auf eine interne Route (voller Neuladevorgang), ein
// Hook in einer Bedingung.
import nextPlugin from "@next/eslint-plugin-next";
import tseslint from "typescript-eslint";

import rootConfig from "../../eslint.config.mjs";

export default tseslint.config(
  { ignores: [".next/**", "next-env.d.ts", "node_modules/**"] },
  // Die Wurzelkonfiguration bringt js.configs.recommended und
  // tseslint.configs.recommended in dieser Reihenfolge mit. Sie hier erneut
  // einzuhaengen wuerde 'no-undef' wieder einschalten, das typescript-eslint
  // fuer TS-Dateien absichtlich abschaltet - TypeScript prueft das besser.
  ...rootConfig,
  {
    files: ["**/*.ts", "**/*.tsx"],
    plugins: { "@next/next": nextPlugin },
    languageOptions: {
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: {
        AbortController: "readonly",
        DOMException: "readonly",
        clearTimeout: "readonly",
        console: "readonly",
        document: "readonly",
        fetch: "readonly",
        performance: "readonly",
        process: "readonly",
        setTimeout: "readonly",
        window: "readonly",
      },
    },
    rules: {
      ...nextPlugin.configs.recommended.rules,
      ...nextPlugin.configs["core-web-vitals"].rules,
    },
  },
);
