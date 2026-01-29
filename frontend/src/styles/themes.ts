/**
 * Theme system for Smart Kanban.
 *
 * Includes standard dark/light themes plus a "HUD mode" for monitoring.
 */

export interface Theme {
  name: string;
  displayName: string;
  colors: {
    primary: string;
    secondary: string;
    panel: string;
    textHigh: string;
    textNormal: string;
    textLow: string;
    brand: string;
    border?: string;
    accent?: string;
    success?: string;
    warning?: string;
    error?: string;
  };
  effects?: {
    glow?: boolean;
    scanlines?: boolean;
    blur?: boolean;
  };
}

export const themes: Record<string, Theme> = {
  dark: {
    name: 'dark',
    displayName: 'Dark',
    colors: {
      primary: 'hsl(220, 20%, 10%)',
      secondary: 'hsl(220, 15%, 15%)',
      panel: 'hsl(220, 15%, 18%)',
      textHigh: 'hsl(0, 0%, 95%)',
      textNormal: 'hsl(0, 0%, 80%)',
      textLow: 'hsl(0, 0%, 50%)',
      brand: 'hsl(25, 82%, 54%)', // Orange
      border: 'hsl(220, 15%, 25%)',
      accent: 'hsl(220, 15%, 22%)',
      success: 'hsl(142, 71%, 45%)',
      warning: 'hsl(38, 92%, 50%)',
      error: 'hsl(0, 72%, 51%)',
    },
  },

  light: {
    name: 'light',
    displayName: 'Light',
    colors: {
      primary: 'hsl(0, 0%, 100%)',
      secondary: 'hsl(0, 0%, 96%)',
      panel: 'hsl(0, 0%, 98%)',
      textHigh: 'hsl(0, 0%, 5%)',
      textNormal: 'hsl(0, 0%, 20%)',
      textLow: 'hsl(0, 0%, 50%)',
      brand: 'hsl(25, 82%, 54%)',
      border: 'hsl(0, 0%, 90%)',
      accent: 'hsl(0, 0%, 94%)',
      success: 'hsl(142, 71%, 45%)',
      warning: 'hsl(38, 92%, 50%)',
      error: 'hsl(0, 72%, 51%)',
    },
  },

  hud: {
    name: 'hud',
    displayName: 'HUD (Monitoring)',
    colors: {
      primary: 'hsl(200, 80%, 5%)',
      secondary: 'hsl(200, 60%, 8%)',
      panel: 'hsl(200, 50%, 12%)',
      textHigh: 'hsl(180, 100%, 70%)',
      textNormal: 'hsl(180, 80%, 50%)',
      textLow: 'hsl(180, 40%, 35%)',
      brand: 'hsl(120, 100%, 50%)', // Green accent
      border: 'hsl(180, 100%, 30%)',
      accent: 'hsl(180, 100%, 15%)',
      success: 'hsl(120, 100%, 50%)',
      warning: 'hsl(60, 100%, 50%)',
      error: 'hsl(0, 100%, 50%)',
    },
    effects: {
      glow: true,
      scanlines: true,
    },
  },
};

/**
 * Apply theme to document root.
 */
export function applyTheme(themeName: string) {
  const theme = themes[themeName];
  if (!theme) {
    console.warn(`Theme "${themeName}" not found`);
    return;
  }

  const root = document.documentElement;

  // Apply color CSS variables
  Object.entries(theme.colors).forEach(([key, value]) => {
    root.style.setProperty(`--color-${key}`, value);
  });

  // Apply theme class
  root.classList.remove('theme-dark', 'theme-light', 'theme-hud');
  root.classList.add(`theme-${theme.name}`);

  // Apply effects
  if (theme.effects?.glow) {
    root.classList.add('effect-glow');
  } else {
    root.classList.remove('effect-glow');
  }

  if (theme.effects?.scanlines) {
    root.classList.add('effect-scanlines');
  } else {
    root.classList.remove('effect-scanlines');
  }
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
