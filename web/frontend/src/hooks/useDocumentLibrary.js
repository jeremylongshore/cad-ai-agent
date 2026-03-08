import { useState, useCallback, useEffect } from 'react';
import {
  listDocuments,
  uploadDocument,
  deleteDocument,
  loadDocument,
  getStorageUsage,
  reconnectSession,
  compareLibraryDocuments,
} from '../lib/api';

export function useDocumentLibrary(isAuthenticated) {
  const [documents, setDocuments] = useState([]);
  const [activeDocumentId, setActiveDocumentId] = useState(null);
  const [storageUsage, setStorageUsage] = useState(null);
  const [libraryLoading, setLibraryLoading] = useState(false);
  const [libraryError, setLibraryError] = useState(null);

  const fetchDocuments = useCallback(async () => {
    if (!isAuthenticated) return;
    setLibraryLoading(true);
    try {
      const data = await listDocuments();
      setDocuments(data.documents || []);
    } catch (err) {
      setLibraryError(err.message);
    } finally {
      setLibraryLoading(false);
    }
  }, [isAuthenticated]);

  const fetchUsage = useCallback(async () => {
    if (!isAuthenticated) return;
    try {
      const data = await getStorageUsage();
      setStorageUsage(data);
    } catch (err) {
      console.warn('[cad] Storage usage fetch failed:', err.message);
    }
  }, [isAuthenticated]);

  // Fetch on mount when authenticated
  useEffect(() => {
    if (isAuthenticated) {
      fetchDocuments();
      fetchUsage();
    }
  }, [isAuthenticated, fetchDocuments, fetchUsage]);

  const uploadToLibrary = useCallback(async (file) => {
    setLibraryLoading(true);
    setLibraryError(null);
    try {
      const data = await uploadDocument(file);
      await fetchDocuments();
      await fetchUsage();
      return data;
    } catch (err) {
      setLibraryError(err.message);
      throw err;
    } finally {
      setLibraryLoading(false);
    }
  }, [fetchDocuments, fetchUsage]);

  const deleteFromLibrary = useCallback(async (docId) => {
    setLibraryError(null);
    try {
      await deleteDocument(docId);
      if (activeDocumentId === docId) {
        setActiveDocumentId(null);
        localStorage.removeItem('intentcad_active_document_id');
      }
      await fetchDocuments();
      await fetchUsage();
    } catch (err) {
      setLibraryError(err.message);
    }
  }, [activeDocumentId, fetchDocuments, fetchUsage]);

  const loadFromLibrary = useCallback(async (docId) => {
    setLibraryLoading(true);
    setLibraryError(null);
    try {
      const data = await loadDocument(docId);
      setActiveDocumentId(docId);
      localStorage.setItem('intentcad_active_document_id', docId);
      return data;
    } catch (err) {
      setLibraryError(err.message);
      throw err;
    } finally {
      setLibraryLoading(false);
    }
  }, []);

  // Reconnect on mount (refresh survival)
  const tryReconnect = useCallback(async () => {
    const savedDocId = localStorage.getItem('intentcad_active_document_id');
    if (!savedDocId || !isAuthenticated) return null;
    try {
      const data = await reconnectSession(savedDocId);
      setActiveDocumentId(savedDocId);
      return data;
    } catch (err) {
      localStorage.removeItem('intentcad_active_document_id');
      return null;
    }
  }, [isAuthenticated]);

  const compareDocuments = useCallback(async (masterDocId, revisionDocId, profile = null) => {
    setLibraryLoading(true);
    setLibraryError(null);
    try {
      return await compareLibraryDocuments(masterDocId, revisionDocId, profile);
    } catch (err) {
      setLibraryError(err.message);
      throw err;
    } finally {
      setLibraryLoading(false);
    }
  }, []);

  const clearLibraryError = useCallback(() => setLibraryError(null), []);

  return {
    documents,
    activeDocumentId,
    setActiveDocumentId,
    storageUsage,
    libraryLoading,
    libraryError,
    clearLibraryError,
    fetchDocuments,
    fetchUsage,
    uploadToLibrary,
    deleteFromLibrary,
    loadFromLibrary,
    tryReconnect,
    compareDocuments,
  };
}
