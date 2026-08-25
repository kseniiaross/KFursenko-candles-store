
import React, { useEffect } from "react";
 
export type ThemeMode = "light";
 
type ThemeContextValue = {
  theme: ThemeMode;
  setTheme: (theme: ThemeMode) => void;
  toggleTheme: () => void;
};
 
const STORAGE_KEY = "site_theme";
 
const VALUE: ThemeContextValue = {
  theme: "light",
  setTheme: () => {},
  toggleTheme: () => {},
};
 
export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  useEffect(() => {
    document.documentElement.dataset.theme = "light";
    document.documentElement.style.colorScheme = "light";
    // drop any stale "dark" left in storage from the old switcher
    window.localStorage.removeItem(STORAGE_KEY);
  }, []);
 
  return <>{children}</>;
};
 
export function useTheme(): ThemeContextValue {
  return VALUE;
}
 
