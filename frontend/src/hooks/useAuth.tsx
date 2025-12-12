import React, { createContext, useContext, useEffect, useState } from "react";
import { setAuthToken } from "../api/client";
import { useLogin, useCurrentUser } from "../api/hooks";
import { User } from "../api/types";

interface AuthContextValue {
  user: User | null;
  token: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [token, setTokenState] = useState<string | null>(localStorage.getItem("token"));
  const [user, setUser] = useState<User | null>(null);
  const loginMutation = useLogin();
  const meQuery = useCurrentUser();

  useEffect(() => {
    if (token) {
      setAuthToken(token);
    }
  }, [token]);

  useEffect(() => {
    if (meQuery.data) {
      setUser(meQuery.data);
    }
  }, [meQuery.data]);

  const login = async (email: string, password: string) => {
    const res = await loginMutation.mutateAsync({ email, password });
    setTokenState(res.access_token);
    setAuthToken(res.access_token);
    await meQuery.refetch();
  };

  const logout = () => {
    setTokenState(null);
    setUser(null);
    setAuthToken(null);
  };

  return <AuthContext.Provider value={{ user, token, login, logout }}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
};
