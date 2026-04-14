import { createAsyncThunk, createSlice, type PayloadAction } from "@reduxjs/toolkit";
import { lumiereReply } from "../services/lumiere";
import type { Locale, LumiereMessage, LumiereSuggestion, LumiereReplyResult } from "../types/lumiere";
import type { RootState } from "./index";

type LumiereState = {
  isOpen: boolean;
  locale: Locale;
  speak: boolean;
  userName: string | null;
  messages: LumiereMessage[];
  status: "idle" | "loading" | "error";
  error: string | null;
};

const initialState: LumiereState = {
  isOpen: false,
  locale: "en",
  speak: false,
  userName: null,
  messages: [],
  status: "idle",
  error: null,
};

// How many messages we send as history context (keep token usage reasonable)
const HISTORY_WINDOW = 10;

function uid(prefix = "m"): string {
  return `${prefix}_${Math.random().toString(16).slice(2)}_${Date.now()}`;
}

// ─── Localized strings ───────────────────────────────────────────────────────

function buildGreeting(locale: Locale, namePart: string): string {
  switch (locale) {
    case "ru":
      return `Bonjour${namePart}! Я Lumière ✨ Ваш персональный консультант по свечам. Расскажите — вы ищете что-то для себя или в подарок?`;
    case "es":
      return `Bonjour${namePart}! Soy Lumière ✨ Tu consultora personal de velas. ¿Buscas algo para ti o es un regalo?`;
    case "fr":
      return `Bonjour${namePart}! Je suis Lumière ✨ Votre consultante personnelle en bougies. Cherchez-vous quelque chose pour vous ou pour offrir?`;
    default:
      return `Bonjour${namePart}! I'm Lumière ✨ Your personal candle consultant. Are you looking for something for yourself, or is this a gift?`;
  }
}

function buildNameQuestion(locale: Locale): string {
  switch (locale) {
    case "ru":
      return "Как к вам обращаться?";
    case "es":
      return "¿Cómo te llamas?";
    case "fr":
      return "Comment puis-je vous appeler?";
    default:
      return "What's your name? I'd love to make this more personal.";
  }
}

function buildErrorMessage(locale: Locale): string {
  switch (locale) {
    case "ru":
      return "Извини, что-то пошло не так. Попробуй ещё раз.";
    case "es":
      return "Lo siento, algo salió mal. Por favor, inténtalo de nuevo.";
    case "fr":
      return "Désolée, quelque chose s'est mal passé. Veuillez réessayer.";
    default:
      return "Sorry, something went wrong. Please try again.";
  }
}

// ─── Thunk ───────────────────────────────────────────────────────────────────

export const sendLumiereMessage = createAsyncThunk<
  LumiereReplyResult,
  { text: string; page?: string },
  { state: RootState; rejectValue: string }
>("lumiere/send", async ({ text, page = "" }, thunkApi) => {
  try {
    const { locale, userName, messages } = thunkApi.getState().lumiere;

    // Build history from recent messages (exclude system/greeting noise, keep real conversation)
    const history = messages
      .filter((m) => m.role === "user" || m.role === "assistant")
      .slice(-HISTORY_WINDOW)
      .map((m) => ({ role: m.role, text: m.text }));

    const result = await lumiereReply({
      text,
      locale,
      userName,
      page,
      history,
    });

    return result;
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "Failed to get assistant reply.";
    return thunkApi.rejectWithValue(msg);
  }
});

// ─── Slice ───────────────────────────────────────────────────────────────────

const lumiereSlice = createSlice({
  name: "lumiere",
  initialState,
  reducers: {
    open: (state) => { state.isOpen = true; },
    close: (state) => { state.isOpen = false; },
    toggle: (state) => { state.isOpen = !state.isOpen; },

    setLocale: (state, action: PayloadAction<Locale>) => {
      state.locale = action.payload;
    },
    setSpeak: (state, action: PayloadAction<boolean>) => {
      state.speak = action.payload;
    },
    setUserName: (state, action: PayloadAction<string | null>) => {
      const v = (action.payload ?? "").trim();
      state.userName = v ? v : null;
    },

    addUserMessage: (state, action: PayloadAction<string>) => {
      const text = action.payload.trim();
      if (!text) return;
      state.messages.push({
        id: uid("u"),
        role: "user",
        text,
        createdAt: Date.now(),
      });
    },

    addAssistantMessage: (
      state,
      action: PayloadAction<{ text: string; suggestions?: LumiereSuggestion[] }>
    ) => {
      const text = action.payload.text.trim();
      if (!text) return;
      state.messages.push({
        id: uid("a"),
        role: "assistant",
        text,
        suggestions: action.payload.suggestions,
        createdAt: Date.now(),
      });
    },

    ensureGreeting: (
      state,
      action: PayloadAction<{ isLoggedIn: boolean; firstName: string | null }>
    ) => {
      if (state.messages.length > 0) return;

      const { isLoggedIn, firstName } = action.payload;

      if (isLoggedIn && firstName?.trim()) {
        state.userName = firstName.trim();
      }

      const namePart = state.userName ? `, ${state.userName}` : "";

      state.messages.push({
        id: uid("a"),
        role: "assistant",
        text: buildGreeting(state.locale, namePart),
        createdAt: Date.now(),
      });

      // Ask for name only for guests who haven't introduced themselves
      if (!isLoggedIn && !state.userName) {
        state.messages.push({
          id: uid("a"),
          role: "assistant",
          text: buildNameQuestion(state.locale),
          createdAt: Date.now(),
        });
      }
    },

    clearChat: (state) => {
      state.messages = [];
      state.status = "idle";
      state.error = null;
    },
  },

  extraReducers: (builder) => {
    builder
      .addCase(sendLumiereMessage.pending, (state) => {
        state.status = "loading";
        state.error = null;
      })
      .addCase(sendLumiereMessage.fulfilled, (state, action) => {
        state.status = "idle";
        state.error = null;
        state.messages.push({
          id: uid("a"),
          role: "assistant",
          text: action.payload.text,
          suggestions: action.payload.suggestions,
          createdAt: Date.now(),
        });
      })
      .addCase(sendLumiereMessage.rejected, (state, action) => {
        state.status = "error";
        state.error = action.payload ?? "Failed to get assistant reply.";
        // Show error inline in chat so user sees it
        state.messages.push({
          id: uid("err"),
          role: "assistant",
          text: buildErrorMessage(state.locale),
          createdAt: Date.now(),
        });
      });
  },
});

export const {
  open,
  close,
  toggle,
  setLocale,
  setSpeak,
  setUserName,
  addUserMessage,
  addAssistantMessage,
  ensureGreeting,
  clearChat,
} = lumiereSlice.actions;

export default lumiereSlice.reducer;