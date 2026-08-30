import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getSettings } from '../api/settings';
import { setActiveTimeZone } from '../utils/format';
import { translations, weekdayShort } from './translations';
import type { Lang, TranslationKey } from './translations';

const LANG_STORAGE_KEY = 'app.language';
const TZ_STORAGE_KEY = 'app.timezone';

export type TranslateParams = Record<string, string | number>;

interface I18nContextValue {
  lang: Lang;
  timezone: string | null;
  weekdays: string[];
  t: (key: TranslationKey, params?: TranslateParams) => string;
}

const isLang = (v: string | null): v is Lang => v === 'ja' || v === 'en';

export const storedLang = (): Lang => {
  const v = localStorage.getItem(LANG_STORAGE_KEY);
  return isLang(v) ? v : 'ja';
};

/**
 * I18nProvider の外（＝ログイン前）でも使える翻訳。
 * ログイン画面は利用者設定を取りに行けないので、前回の言語を localStorage から使う。
 */
export const translate = (key: TranslationKey, params?: TranslateParams): string => {
  const lang = storedLang();
  let text = translations[lang][key] ?? translations.ja[key] ?? key;
  if (params) {
    for (const [name, value] of Object.entries(params)) {
      text = text.replace(new RegExp(`\\{${name}\\}`, 'g'), String(value));
    }
  }
  return text;
};

const I18nContext = createContext<I18nContextValue>({
  lang: 'ja',
  timezone: null,
  weekdays: weekdayShort.ja,
  t: (key) => translations.ja[key] ?? key,
});

export const I18nProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [lang, setLang] = useState<Lang>(storedLang);
  const [timezone, setTimezone] = useState<string | null>(() => localStorage.getItem(TZ_STORAGE_KEY));

  const { data: settings } = useQuery({ queryKey: ['settings'], queryFn: getSettings });

  // サーバー側の設定を正として反映し、次回初期表示用にローカルにも保存する
  useEffect(() => {
    if (!settings) return;
    if (isLang(settings.language)) {
      setLang(settings.language);
      localStorage.setItem(LANG_STORAGE_KEY, settings.language);
    }
    if (settings.timezone) {
      setTimezone(settings.timezone);
      localStorage.setItem(TZ_STORAGE_KEY, settings.timezone);
    }
  }, [settings]);

  // 「今日」の判定を行う日付ユーティリティへタイムゾーンを伝える
  useEffect(() => {
    setActiveTimeZone(timezone);
  }, [timezone]);

  const t = useCallback((key: TranslationKey, params?: TranslateParams): string => {
    let text = translations[lang][key] ?? translations.ja[key] ?? key;
    if (params) {
      for (const [name, value] of Object.entries(params)) {
        text = text.replaceAll(`{${name}}`, String(value));
      }
    }
    return text;
  }, [lang]);

  return (
    <I18nContext.Provider value={{ lang, timezone, weekdays: weekdayShort[lang], t }}>
      {children}
    </I18nContext.Provider>
  );
};

// eslint-disable-next-line react-refresh/only-export-components
export const useI18n = (): I18nContextValue => useContext(I18nContext);
