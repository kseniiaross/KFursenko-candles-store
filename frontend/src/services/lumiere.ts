import api from "../api/axiosInstance";
import type { Locale, LumiereSuggestion, LumiereReplyResult } from "../types/lumiere";

type LumiereHistoryMessage = {
  role: "user" | "assistant";
  text: string;
};

type LumiereReplyInput = {
  text: string;
  locale: Locale;
  userName: string | null;
  page?: string;
  history?: LumiereHistoryMessage[];
};

export async function lumiereReply(input: LumiereReplyInput): Promise<LumiereReplyResult> {
  const resp = await api.post<LumiereReplyResult>("/lumiere/reply/", {
    text: input.text,
    locale: input.locale,
    userName: input.userName,
    page: input.page ?? "",
    history: input.history ?? [],
  });

  const data = resp.data;
  return {
    text: String(data?.text ?? ""),
    suggestions: Array.isArray(data?.suggestions)
      ? (data.suggestions as LumiereSuggestion[])
      : undefined,
  };
}