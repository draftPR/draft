/**
 * i18n configuration using i18next + react-i18next.
 *
 * English-only for now, but infrastructure is ready for more languages.
 * Import this file early in main.tsx to initialize translations.
 */

import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./locales/en.json";

i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
  },
  lng: "en",
  fallbackLng: "en",
  interpolation: {
    escapeValue: false, // React already escapes
  },
});

export default i18n;
