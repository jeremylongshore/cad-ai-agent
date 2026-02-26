import { useState, useCallback } from 'react';
import { uploadFile, planEdit, applyChanges, downloadFile, getRenderBlob, clearHistory } from '../lib/api';

const NO_CHANGES_MESSAGE = "I couldn't plan any changes. Try being more specific about which element to edit.";

export function useSession() {
  const [sessionId, setSessionId] = useState(null);
  const [fileInfo, setFileInfo] = useState(null);
  const [messages, setMessages] = useState([]);
  const [operations, setOperations] = useState([]);
  const [selectedOps, setSelectedOps] = useState([]);
  const [validation, setValidation] = useState(null);
  const [previewUrls, setPreviewUrls] = useState({ original: null, edited: null, diff: null });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const clearError = useCallback(() => setError(null), []);

  const upload = useCallback(async (file) => {
    setLoading(true);
    setError(null);
    try {
      const data = await uploadFile(file);
      setSessionId(data.session_id);
      setFileInfo(data.file_info);
      try {
        const blob = await getRenderBlob(data.session_id, 'original');
        const url = URL.createObjectURL(blob);
        setPreviewUrls((prev) => ({ ...prev, original: url }));
      } catch (renderErr) {
        console.warn('[cad] Original render fetch failed:', renderErr.message);
      }
      setMessages([{ role: 'system', text: `Loaded ${file.name} (${data.file_info.entity_count} entities, ${data.file_info.layer_count} layers)` }]);
      setOperations([]);
      setSelectedOps([]);
      setValidation(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const sendPrompt = useCallback(async (prompt) => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    setMessages((prev) => [...prev, { role: 'user', text: prompt }]);

    try {
      const data = await planEdit(sessionId, prompt);
      const ops = data.operations || [];
      setOperations(ops);
      setSelectedOps(ops.map((_, i) => i));
      setValidation(data.validation || null);

      // Determine AI response text
      let aiText;
      if (ops.length === 0 && data.message) {
        aiText = data.message;
      } else if (ops.length === 0) {
        aiText = NO_CHANGES_MESSAGE;
      } else {
        aiText = data.summary || `${ops.length} operation(s) planned.`;
      }
      setMessages((prev) => [...prev, { role: 'ai', text: aiText }]);

      if (data.preview_url) {
        setPreviewUrls((prev) => ({ ...prev, edited: data.preview_url }));
      }
    } catch (err) {
      setError(err.message);
      setMessages((prev) => [...prev, { role: 'ai', text: `Error: ${err.message}` }]);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  const toggleOp = useCallback((index) => {
    setSelectedOps((prev) =>
      prev.includes(index) ? prev.filter((i) => i !== index) : [...prev, index]
    );
  }, []);

  const apply = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await applyChanges(sessionId, selectedOps);
      setMessages((prev) => [...prev, { role: 'system', text: data.message || 'Changes applied.' }]);

      try {
        const blob = await getRenderBlob(sessionId, 'edited');
        const url = URL.createObjectURL(blob);
        setPreviewUrls((prev) => ({ ...prev, edited: url }));
      } catch (renderErr) {
        console.warn('[cad] Edited render fetch failed:', renderErr.message);
        setMessages((prev) => [...prev, {
          role: 'system',
          text: 'Preview not available — download the edited DXF to view.',
        }]);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [sessionId, selectedOps]);

  const download = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      await downloadFile(sessionId);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  const clearConversation = useCallback(async () => {
    if (!sessionId) return;
    try {
      await clearHistory(sessionId);
    } catch (err) {
      console.warn('[cad] Clear history API failed:', err.message);
    }
    setMessages([]);
    setOperations([]);
    setSelectedOps([]);
    setValidation(null);
  }, [sessionId]);

  const reset = useCallback(() => {
    // Revoke blob URLs to free memory
    Object.values(previewUrls).forEach((url) => {
      if (url) URL.revokeObjectURL(url);
    });
    setSessionId(null);
    setFileInfo(null);
    setMessages([]);
    setOperations([]);
    setSelectedOps([]);
    setValidation(null);
    setPreviewUrls({ original: null, edited: null, diff: null });
    setError(null);
  }, [previewUrls]);

  return {
    sessionId,
    fileInfo,
    messages,
    operations,
    selectedOps,
    validation,
    previewUrls,
    loading,
    error,
    clearError,
    upload,
    sendPrompt,
    toggleOp,
    apply,
    download,
    clearConversation,
    reset,
  };
}
