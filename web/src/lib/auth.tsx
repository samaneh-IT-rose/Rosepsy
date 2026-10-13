import { createContext, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { api, setToken, clearToken, getToken } from './api';

interface AuthCtx {
  signedIn: boolean;
  loading: boolean;
  signIn: (token: string) => void;
  signOut: () => void;
}

const AuthContext = createContext<AuthCtx>({
  signedIn: false,
  loading: true,
  signIn: () => {},
  signOut: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [signedIn, setSignedIn] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (getToken()) setSignedIn(true);
    setLoading(false);
  }, []);

  const signIn = (t: string) => {
    setToken(t);
    setSignedIn(true);
  };

  const signOut = () => {
    clearToken();
    setSignedIn(false);
  };

  return (
    <AuthContext.Provider value={{ signedIn, loading, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);