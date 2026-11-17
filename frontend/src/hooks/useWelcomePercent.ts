import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { getTerms } from "../api/auth";

/** The sign-up discount's percent, from the terms a new account accepts on
 *  Register (/accounts/terms/), so every page that advertises it names the
 *  same figure as the terms. null while loading, if the request fails, or
 *  when no sign-up discount is running: pages then name no figure. */
export function useWelcomePercent(): number | null {
  const { i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const [percent, setPercent] = useState<number | null>(null);

  useEffect(() => {
    let active = true;

    getTerms(locale)
      .then((terms) => {
        if (active) setPercent(terms?.percent ?? null);
      })
      .catch(() => {});

    return () => {
      active = false;
    };
  }, [locale]);

  return percent;
}
