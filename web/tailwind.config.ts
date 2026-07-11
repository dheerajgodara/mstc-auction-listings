import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  darkMode: ["selector", '[data-theme="dark"]'],
  theme: {
    /* Airbnb marketplace shells (audit §14) — not Apple 734/834/1068/1441 */
    screens: {
      sm: "744px",
      md: "950px",
      lg: "1128px",
      xl: "1440px",
    },
    extend: {
      colors: {
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        card: "hsl(var(--card))",
        muted: "hsl(var(--muted))",
        "muted-foreground": "hsl(var(--muted-foreground))",
        border: "hsl(var(--border))",
        primary: "hsl(var(--primary))",
        "primary-foreground": "hsl(var(--primary-foreground))",
        accent: "hsl(var(--accent))",
        action: "var(--color-action)",
        babu: "var(--color-babu)",
        arches: "var(--color-arches)",
        hof: "var(--color-hof)",
        "marketplace-gray": {
          50: "var(--color-gray-50)",
          100: "var(--color-gray-100)",
          200: "var(--color-gray-200)",
          300: "var(--color-gray-300)",
          500: "var(--color-gray-500)",
          600: "var(--color-gray-600)",
        },
      },
      borderRadius: {
        lg: "var(--radius-lg)",
        DEFAULT: "var(--radius)",
        xs: "var(--radius-xs)",
        sm: "var(--radius-sm)",
        xl: "var(--radius-xl)",
        md: "var(--radius-md)",
        pill: "var(--radius-pill)",
      },
      spacing: {
        "marketplace-2": "var(--space-2)",
        "marketplace-4": "var(--space-4)",
        "marketplace-8": "var(--space-8)",
        "marketplace-16": "var(--space-16)",
        "marketplace-24": "var(--space-24)",
        "marketplace-32": "var(--space-32)",
        "marketplace-56": "var(--space-56)",
        "marketplace-96": "var(--space-96)",
        "nav-regular": "var(--nav-height-regular)",
        "nav-compact": "var(--nav-height-compact)",
      },
      boxShadow: {
        subtle: "var(--shadow-subtle)",
        hover: "var(--shadow-hover)",
        modal: "var(--shadow-modal)",
        "listing-card": "var(--shadow-subtle)",
      },
      zIndex: {
        globalnav: "var(--z-globalnav)",
        ribbon: "var(--z-ribbon)",
        sticky: "var(--z-sticky)",
        modal: "var(--z-modal)",
      },
      fontFamily: {
        sans: ["var(--font-text)"],
        display: ["var(--font-display)"],
      },
      transitionDuration: {
        instant: "var(--duration-instant)",
        fast: "var(--duration-fast)",
        hover: "var(--duration-hover)",
        control: "var(--duration-control)",
        nav: "var(--duration-nav)",
        accordion: "var(--duration-accordion)",
        ribbon: "var(--duration-ribbon)",
      },
      transitionTimingFunction: {
        marketplace: "var(--ease-marketplace-nav)",
        standard: "var(--ease-standard)",
        "out-soft": "var(--ease-out-soft)",
      },
    },
  },
  plugins: [],
};

export default config;
