export type Locale = "en" | "ru" | "es" | "fr";
export type LumiereRole = "assistant" | "user";

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
};

export type LumiereReplyResult = {
  text: string;
  suggestions?: LumiereSuggestion[];
};