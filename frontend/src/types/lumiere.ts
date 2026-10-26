export type Locale = "en" | "ru" | "es" | "fr";
export type LumiereRole = "assistant" | "user";
export type LumiereStatus = "idle" | "loading" | "failed";

export type LumiereSuggestion = {
  id: number;
  name: string;
  slug: string;
  price: string;
  in_stock: boolean;
};

export type LumiereMessage = {
  id: string;
  role: LumiereRole;
  text: string;
  createdAt: number;
  suggestions?: LumiereSuggestion[];
  // Set on Lumière's greeting only: the one message whose text follows the
  // panel's language when it changes.
  greeting?: { name: string | null };
};

export type LumiereReplyResult = {
  text: string;
  suggestions?: LumiereSuggestion[];
};

export type LumiereHistoryMessage = {
  role: LumiereRole;
  text: string;
};

export type LumiereReplyInput = {
  text: string;
  locale: Locale;
  userName: string | null;
  page?: string;
  history?: LumiereHistoryMessage[];
};

export type LumierePersistedState = {
  locale: Locale;
  speak: boolean;
  userName: string | null;
  messages: LumiereMessage[];
};