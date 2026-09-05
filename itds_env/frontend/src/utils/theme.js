const APP_SETTINGS_KEY = 'appSettings';
export const THEME_LIGHT = 'light';
export const THEME_DARK = 'dark';

const isBrowser = typeof window !== 'undefined' && typeof document !== 'undefined';

const safeParseJson = (value) => {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
};

export const getStoredThemeMode = () => {
  if (!isBrowser) return THEME_LIGHT;

  const storedSettings = safeParseJson(window.localStorage.getItem(APP_SETTINGS_KEY) || 'null');
  if (storedSettings && typeof storedSettings.darkMode === 'boolean') {
    return storedSettings.darkMode ? THEME_DARK : THEME_LIGHT;
  }

  const prefersDark = window.matchMedia?.('(prefers-color-scheme: dark)')?.matches;
  return prefersDark ? THEME_DARK : THEME_LIGHT;
};

export const applyThemeMode = (mode) => {
  if (!isBrowser) return THEME_LIGHT;

  const nextMode = mode === THEME_DARK ? THEME_DARK : THEME_LIGHT;
  const root = document.documentElement;
  root.setAttribute('data-theme', nextMode);
  root.style.colorScheme = nextMode;
  if (document.body) {
    document.body.setAttribute('data-theme', nextMode);
  }
  return nextMode;
};

export const applyThemeFromStorage = () => applyThemeMode(getStoredThemeMode());

export const isDarkThemeEnabled = () => getStoredThemeMode() === THEME_DARK;