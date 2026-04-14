export type User = {
  id: number;
  email: string;
  first_name?: string;
  last_name?: string;
};

export type AuthState = {
  token: string | null;
  user: User | null;
  isLoggedIn: boolean;
};