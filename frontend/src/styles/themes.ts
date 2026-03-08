/**
 * Theme system for Draft.
 *
 * Maps theme colors to shadcn/ui CSS variables so the entire component
 * library (buttons, cards, popovers, inputs, etc.) responds correctly.
 *
 * Includes standard dark/light themes plus a "HUD mode" for monitoring.
 */

export interface Theme {
  name: string;
  displayName: string;
  colors: {
    /** Page background */
    background: string;
    /** Main text color */
    foreground: string;
    /** Card / panel background */
    card: string;
    /** Text on cards */
    cardForeground: string;
    /** Popover / dropdown background */
    popover: string;
    /** Text in popovers */
    popoverForeground: string;
    /** Primary accent (buttons, links) */
    primary: string;
    /** Text on primary accent */
    primaryForeground: string;
    /** Secondary / muted background */
    secondary: string;
    /** Text on secondary background */
    secondaryForeground: string;
    /** Muted background (badges, subtle fills) */
    muted: string;
    /** Muted text / placeholders */
    mutedForeground: string;
    /** Accent highlight background */
    accent: string;
    /** Text on accent background */
    accentForeground: string;
    /** Destructive / error actions */
    destructive: string;
    /** Text on destructive background */
    destructiveForeground: string;
    /** Borders */
    border: string;
    /** Input borders */
    input: string;
    /** Focus ring color */
    ring: string;
  };
  effects?: {
    glow?: boolean;
    scanlines?: boolean;
  };
}

export const themes: Record<string, Theme> = {
  dark: {
    name: 'dark',
    displayName: 'Dark',
    colors: {
      background: 'hsl(220 20% 10%)',
      foreground: 'hsl(0 0% 95%)',
      card: 'hsl(220 15% 13%)',
      cardForeground: 'hsl(0 0% 95%)',
      popover: 'hsl(220 15% 13%)',
      popoverForeground: 'hsl(0 0% 95%)',
      primary: 'hsl(25 82% 54%)',        // Orange brand
      primaryForeground: 'hsl(0 0% 100%)',
      secondary: 'hsl(220 15% 18%)',
      secondaryForeground: 'hsl(0 0% 80%)',
      muted: 'hsl(220 15% 18%)',
      mutedForeground: 'hsl(0 0% 50%)',
      accent: 'hsl(220 15% 22%)',
      accentForeground: 'hsl(0 0% 90%)',
      destructive: 'hsl(0 72% 51%)',
      destructiveForeground: 'hsl(0 0% 100%)',
      border: 'hsl(220 15% 25%)',
      input: 'hsl(220 15% 25%)',
      ring: 'hsl(25 82% 54%)',
    },
  },

  light: {
    name: 'light',
    displayName: 'Light',
    colors: {
      background: 'hsl(0 0% 98%)',
      foreground: 'hsl(0 0% 10%)',
      card: 'hsl(0 0% 100%)',
      cardForeground: 'hsl(0 0% 10%)',
      popover: 'hsl(0 0% 100%)',
      popoverForeground: 'hsl(0 0% 10%)',
      primary: 'hsl(25 82% 54%)',        // Orange brand
      primaryForeground: 'hsl(0 0% 100%)',
      secondary: 'hsl(0 0% 96%)',
      secondaryForeground: 'hsl(0 0% 10%)',
      muted: 'hsl(0 0% 96%)',
      mutedForeground: 'hsl(0 0% 45%)',
      accent: 'hsl(0 0% 94%)',
      accentForeground: 'hsl(0 0% 10%)',
      destructive: 'hsl(0 84% 60%)',
      destructiveForeground: 'hsl(0 0% 98%)',
      border: 'hsl(0 0% 90%)',
      input: 'hsl(0 0% 90%)',
      ring: 'hsl(25 82% 54%)',
    },
  },

  hud: {
    name: 'hud',
    displayName: 'HUD (Monitoring)',
    colors: {
      background: 'hsl(200 80% 5%)',
      foreground: 'hsl(180 100% 70%)',
      card: 'hsl(200 50% 10%)',
      cardForeground: 'hsl(180 100% 70%)',
      popover: 'hsl(200 50% 10%)',
      popoverForeground: 'hsl(180 100% 70%)',
      primary: 'hsl(120 100% 50%)',      // Green accent
      primaryForeground: 'hsl(200 80% 5%)',
      secondary: 'hsl(200 60% 8%)',
      secondaryForeground: 'hsl(180 80% 50%)',
      muted: 'hsl(200 60% 8%)',
      mutedForeground: 'hsl(180 40% 35%)',
      accent: 'hsl(180 100% 15%)',
      accentForeground: 'hsl(180 100% 70%)',
      destructive: 'hsl(0 100% 50%)',
      destructiveForeground: 'hsl(0 0% 100%)',
      border: 'hsl(180 100% 30%)',
      input: 'hsl(180 100% 30%)',
      ring: 'hsl(120 100% 50%)',
    },
    effects: {
      glow: true,
      scanlines: true,
    },
  },
};

// Map from Theme color keys to CSS variable names (camelCase -> kebab-case)
const COLOR_VAR_MAP: Record<string, string> = {
  background: 'background',
  foreground: 'foreground',
  card: 'card',
  cardForeground: 'card-foreground',
  popover: 'popover',
  popoverForeground: 'popover-foreground',
  primary: 'primary',
  primaryForeground: 'primary-foreground',
  secondary: 'secondary',
  secondaryForeground: 'secondary-foreground',
  muted: 'muted',
  mutedForeground: 'muted-foreground',
  accent: 'accent',
  accentForeground: 'accent-foreground',
  destructive: 'destructive',
  destructiveForeground: 'destructive-foreground',
  border: 'border',
  input: 'input',
  ring: 'ring',
};

/**
 * Apply theme to document root by setting shadcn/ui CSS variables.
 */
export function applyTheme(themeName: string) {
  const theme = themes[themeName];
  if (!theme) {
    console.warn(`Theme "${themeName}" not found`);
    return;
  }

  const root = document.documentElement;

  // Set shadcn CSS variables (--color-background, --color-foreground, etc.)
  for (const [key, value] of Object.entries(theme.colors)) {
    const varName = COLOR_VAR_MAP[key];
    if (varName) {
      root.style.setProperty(`--color-${varName}`, value);
    }
  }

  // Also set the legacy custom vars for HUD CSS compatibility
  root.style.setProperty('--color-textHigh', theme.colors.foreground);
  root.style.setProperty('--color-textNormal', theme.colors.secondaryForeground);
  root.style.setProperty('--color-textLow', theme.colors.mutedForeground);
  root.style.setProperty('--color-brand', theme.colors.primary);

  // Apply theme class
  root.classList.remove('theme-dark', 'theme-light', 'theme-hud');
  root.classList.add(`theme-${theme.name}`);

  // Apply effects
  root.classList.toggle('effect-glow', !!theme.effects?.glow);
  root.classList.toggle('effect-scanlines', !!theme.effects?.scanlines);
}

/**
 * Get current theme name from localStorage or system preference.
 */
export function getCurrentTheme(): string {
  const stored = localStorage.getItem('smart-kanban-theme');
  if (stored && themes[stored]) {
    return stored;
  }

  // Default to dark
  return 'dark';
}

/**
 * Save theme preference to localStorage.
 */
export function saveThemePreference(themeName: string) {
  localStorage.setItem('smart-kanban-theme', themeName);
}
