import { useState, useEffect, useCallback } from 'react';
import {
  auth,
  googleProvider,
  signInWithPopup,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signOut as firebaseSignOut,
  onAuthStateChanged,
} from '../lib/firebase';

// Dev-mode auth bypass — when VITE_DEV_AUTH=1 (set by Playwright), skip Firebase
// and use a synthetic user that matches backend's CAD_WEB_DEV_MODE dev-user.
const DEV_AUTH = import.meta.env.VITE_DEV_AUTH === '1';
const DEV_USER = DEV_AUTH ? {
  uid: 'dev-user',
  email: 'dev@localhost',
  displayName: 'Dev User',
  getIdToken: async () => 'dev-token',
} : null;

export function useAuth() {
  const [user, setUser] = useState(DEV_USER);
  const [loading, setLoading] = useState(!DEV_AUTH);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (DEV_AUTH) return; // Skip Firebase listener in dev auth mode
    const unsubscribe = onAuthStateChanged(auth, (firebaseUser) => {
      setUser(firebaseUser);
      setLoading(false);
    });
    return unsubscribe;
  }, []);

  const clearError = useCallback(() => setError(null), []);

  const signInWithGoogle = useCallback(async () => {
    setError(null);
    try {
      await signInWithPopup(auth, googleProvider);
    } catch (err) {
      setError(formatAuthError(err));
    }
  }, []);

  const signInWithEmail = useCallback(async (email, password) => {
    setError(null);
    try {
      await signInWithEmailAndPassword(auth, email, password);
    } catch (err) {
      setError(formatAuthError(err));
    }
  }, []);

  const signUpWithEmail = useCallback(async (email, password) => {
    setError(null);
    try {
      await createUserWithEmailAndPassword(auth, email, password);
    } catch (err) {
      setError(formatAuthError(err));
    }
  }, []);

  const signOut = useCallback(async () => {
    await firebaseSignOut(auth);
  }, []);

  return {
    user,
    loading,
    error,
    clearError,
    signInWithGoogle,
    signInWithEmail,
    signUpWithEmail,
    signOut,
  };
}

function formatAuthError(err) {
  const map = {
    'auth/email-already-in-use': 'An account with this email already exists.',
    'auth/invalid-email': 'Please enter a valid email address.',
    'auth/wrong-password': 'Incorrect password.',
    'auth/user-not-found': 'No account found with this email.',
    'auth/weak-password': 'Password must be at least 6 characters.',
    'auth/popup-closed-by-user': 'Sign-in popup was closed.',
    'auth/invalid-credential': 'Invalid email or password.',
  };
  return map[err.code] || err.message || 'Authentication failed.';
}
