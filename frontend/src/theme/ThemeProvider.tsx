
import React, { useEffect } from "react";
 
const STORAGE_KEY = "site_theme";
 
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
  
