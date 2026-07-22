import { create } from "zustand";

interface User {
  id: string;
  email: string;
  role: string;
}

interface AuthState {
  token: string | null;
  user: User | null;
  setAuth: (token: string | null, user: User | null) => void;
  clearAuth: () => void;
}

// Fallback demo tokens for local frontend development (can be updated by signup/login flows)
export const useAuthStore = create<AuthState>((set) => ({
  token: process.env.NEXT_PUBLIC_DEMO_TOKEN ?? "mock_jwt_token_for_dev",
  user: {
    id: "00000000-0000-0000-0000-000000000000",
    email: "dev@kynetic.ai",
    role: "admin"
  },
  setAuth: (token, user) => set({ token, user }),
  clearAuth: () => set({ token: null, user: null }),
}));
