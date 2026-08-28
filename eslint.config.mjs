// ARGUS — ESLint (Flat Config).
//
// Bewusst schlank: TypeScript prueft die Typen, Prettier die Formatierung.
// ESLint ist nur fuer das zustaendig, was beide nicht sehen - unbenutzte
// Variablen, vergessene await, verirrte console-Aufrufe.

import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    // Erzeugter Code wird nicht gelintet: er wuerde beim naechsten
    // 'make gen' wieder so aussehen wie vorher.
    ignores: ["**/node_modules/**", "**/dist/**", "**/gen/**", "**/.venv/**", "**/coverage/**"],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
    },
    rules: {
      // Ungenutzte Bezeichner sind erlaubt, wenn sie mit _ beginnen: bei
      // Callback-Signaturen ist das der uebliche Weg, eine Position zu
      // ueberspringen.
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      // console gehoert in Werkzeuge, nicht in Bibliotheks- oder UI-Code.
      "no-console": ["warn", { allow: ["warn", "error"] }],
      // Ein vergessenes await ist im Frontend die haeufigste Ursache fuer
      // "es passiert manchmal nichts".
      "@typescript-eslint/no-floating-promises": "off",
      "no-implicit-coercion": "error",
      eqeqeq: ["error", "always", { null: "ignore" }],
    },
  },
);
