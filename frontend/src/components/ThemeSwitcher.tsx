import React, { useState, useEffect } from 'react';
import { Button } from './ui/button';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from './ui/select';
import { Moon, Sun, Monitor } from 'lucide-react';
import { themes, applyTheme, getCurrentTheme, saveThemePreference } from '../styles/themes';

interface ThemeSwitcherProps {
  /** Display as a dropdown or icon buttons */
  variant?: 'dropdown' | 'buttons';
  /** Optional className for styling */
  className?: string;
}

/**
 * Theme switcher component.
 *
 * Allows users to switch between dark, light, and HUD themes.
 * Saves preference to localStorage.
 *
 * @example
 * ```tsx
 * // Dropdown variant (for settings)
 * <ThemeSwitcher variant="dropdown" />
 *
 * // Button variant (for toolbar)
 * <ThemeSwitcher variant="buttons" />
 * ```
 */
export function ThemeSwitcher({ variant = 'dropdown', className = '' }: ThemeSwitcherProps) {
  const [currentTheme, setCurrentTheme] = useState(getCurrentTheme());

  // Apply theme on mount and when changed
  useEffect(() => {
    applyTheme(currentTheme);
  }, [currentTheme]);

  const handleThemeChange = (themeName: string) => {
    setCurrentTheme(themeName);
    saveThemePreference(themeName);
  };

  if (variant === 'buttons') {
    return (
      <div className={`flex items-center gap-1 ${className}`}>
        <Button
          size="sm"
          variant={currentTheme === 'light' ? 'default' : 'ghost'}
          onClick={() => handleThemeChange('light')}
          title="Light theme"
        >
          <Sun className="h-4 w-4" />
        </Button>
        <Button
          size="sm"
          variant={currentTheme === 'dark' ? 'default' : 'ghost'}
          onClick={() => handleThemeChange('dark')}
          title="Dark theme"
        >
          <Moon className="h-4 w-4" />
        </Button>
        <Button
          size="sm"
          variant={currentTheme === 'hud' ? 'default' : 'ghost'}
          onClick={() => handleThemeChange('hud')}
          title="HUD mode (monitoring)"
        >
          <Monitor className="h-4 w-4" />
        </Button>
      </div>
    );
  }

  return (
    <div className={className}>
      <Select value={currentTheme} onValueChange={handleThemeChange}>
        <SelectTrigger className="w-[180px]">
          <div className="flex items-center gap-2">
            {currentTheme === 'light' && <Sun className="h-4 w-4" />}
            {currentTheme === 'dark' && <Moon className="h-4 w-4" />}
            {currentTheme === 'hud' && <Monitor className="h-4 w-4" />}
            <SelectValue placeholder="Select theme" />
          </div>
        </SelectTrigger>

        <SelectContent>
          <SelectGroup>
            <SelectLabel>Theme</SelectLabel>
            {Object.entries(themes).map(([key, theme]) => (
              <SelectItem key={key} value={key}>
                <div className="flex items-center gap-2">
                  {key === 'light' && <Sun className="h-4 w-4" />}
                  {key === 'dark' && <Moon className="h-4 w-4" />}
                  {key === 'hud' && <Monitor className="h-4 w-4" />}
                  <span>{theme.displayName}</span>
                </div>
              </SelectItem>
            ))}
          </SelectGroup>
        </SelectContent>
      </Select>

      {currentTheme === 'hud' && (
        <p className="mt-2 text-xs text-muted-foreground">
          HUD mode includes glow effects and scanlines for a futuristic monitoring dashboard look.
        </p>
      )}
    </div>
  );
}

/**
 * Hook for programmatic theme switching.
 *
 * @example
 * ```tsx
 * function MyComponent() {
 *   const { theme, setTheme, availableThemes } = useTheme();
 *
 *   return (
 *     <button onClick={() => setTheme('hud')}>
 *       Switch to HUD mode
 *     </button>
 *   );
 * }
 * ```
 */
export function useTheme() {
  const [theme, setThemeState] = useState(getCurrentTheme());

  const setTheme = (themeName: string) => {
    if (!themes[themeName]) {
      console.warn(`Theme "${themeName}" does not exist`);
      return;
    }
    setThemeState(themeName);
    applyTheme(themeName);
    saveThemePreference(themeName);
  };

  return {
    theme,
    setTheme,
    availableThemes: Object.keys(themes),
    themes,
  };
}
