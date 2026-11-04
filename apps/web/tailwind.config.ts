import type { Config } from "tailwindcss";

export default {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: Object.fromEntries(
        [
          "bg",
          "surface",
          "surface-2",
          "border",
          "border-strong",
          "text",
          "text-muted",
          "text-subtle",
          "primary",
          "primary-hover",
          "primary-fg",
          "success",
          "warning",
          "danger",
          "info",
          "focus-ring",
        ].map((name) => [name, `var(--${name})`]),
      ),
      fontSize: Object.fromEntries(
        ["xs", "sm", "base", "md", "lg", "xl"].map((name) => [
          name,
          `var(--text-${name})`,
        ]),
      ),
      width: { control: "var(--control-h)" },
      height: {
        control: "var(--control-h)",
        "control-sm": "var(--control-h-sm)",
        "control-lg": "var(--control-h-lg)",
      },
      borderRadius: { DEFAULT: "var(--radius)", card: "var(--radius-card)" },
    },
  },
  plugins: [],
} satisfies Config;
