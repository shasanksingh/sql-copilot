"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type React from "react";
import { usePathname } from "next/navigation";
import type { AuthUser } from "@/features/api/types";
import { getCurrentUser, logout as logoutRequest } from "@/features/api/client";

type AuthContextValue = {
  user?: AuthUser;
  loading: boolean;
  setUser: (user?: AuthUser) => void;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);
const publicRoutes = ["/login", "/signup", "/forgot-password", "/reset-password"];

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [user, setUser] = useState<AuthUser>();
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    try {
      const response = await getCurrentUser();
      setUser(response.user);
    } catch {
      setUser(undefined);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (publicRoutes.some((route) => pathname === route || pathname.startsWith(`${route}/`))) {
      setLoading(false);
      return;
    }
    void refresh();
  }, [pathname]);

  const logout = async () => {
    try {
      await logoutRequest();
    } finally {
      setUser(undefined);
    }
  };

  const value = useMemo(
    () => ({ user, loading, setUser, refresh, logout }),
    [user, loading]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
