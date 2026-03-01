import { useState, useCallback, useRef } from 'react';
import { uploadFile, planEdit, applyChanges, downloadFile, getRenderBlob, clearHistory, compareFiles, revisionApply, revisionDownloadUrl } from '../lib/api';

const NO_CHANGES_MESSAGE = "I couldn't plan any changes. Try being more specific about which element to edit.";

/** Create a message object with a unique ID and timestamp */
function msg(role, text, extra = {}) {
  return { id: crypto.randomUUID(), role, text, ts: Date.now(), ...extra };
}

export function useSession() {
  const [sessionId, setSessionId] = useState(null);
  const [fileInfo, setFileInfo] = useState(null);
  const [messages, setMessages] = useState([]);
  const [operations, setOperations] = useState([]);
  const [selectedOps, setSelectedOps] = useState([]);
  const [validation, setValidation] = useState(null);
  const [previewUrls, setPreviewUrls] = useState({ original: null, edited: null });
  const [comparisonResult, setComparisonResult] = useState(null);
  const [revisionOps, setRevisionOps] = useState(null);
  const [revisionApplyResult, setRevisionApplyResult] = useState(null);
  const [bundleReady, setBundleReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingStartTime, setLoadingStartTime] = useState(null);
  const [error, setError] = useState(null);

  // Track last user prompt for retry
  const lastPromptRef = useRef(null);

  const clearError = useCallback(() => setError(null), []);

  const upload = useCallback(async (file) => {
    setLoading(true);
    setLoadingStartTime(Date.now());
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
      setMessages([msg('system', `Loaded ${file.name} (${data.file_info.entity_count} entities, ${data.file_info.layer_count} layers)`)]);
      setOperations([]);
      setSelectedOps([]);
      setValidation(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      setLoadingStartTime(null);
    }
  }, []);

  const sendPrompt = useCallback(async (prompt) => {
    if (!sessionId) return;
    const startTime = Date.now();
    setLoading(true);
    setLoadingStartTime(startTime);
    setError(null);
    lastPromptRef.current = prompt;
    setMessages((prev) => [...prev, msg('user', prompt)]);

    try {
      const data = await planEdit(sessionId, prompt);
      const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
      const ops = data.operations || [];
      setOperations(ops);
      setSelectedOps(ops.map((_, i) => i));

      const val = data.validation || null;
      setValidation(val);

      // Build enriched AI response text (H3)
      let aiText;
      if (ops.length === 0 && data.message) {
        aiText = data.message;
      } else if (ops.length === 0) {
        aiText = NO_CHANGES_MESSAGE;
      } else {
        // Include operation descriptions, not just count
        const opLines = ops.map((op, i) =>
          `${i + 1}. ${op.description || op.summary || op.op_type}`
        );
        aiText = `${ops.length} operation(s) planned:\n${opLines.join('\n')}`;
        if (data.summary && data.summary !== 'No operations planned.') {
          aiText += `\n\nSummary: ${data.summary}`;
        }
      }
      setMessages((prev) => [...prev, msg('ai', aiText, { elapsed })]);

      // Surface validation blockers as error messages (C2)
      if (val && val.blockers && val.blockers.length > 0) {
        const blockerText = val.blockers.map((b) => b.message).join('\n');
        setMessages((prev) => [...prev,
          msg('error', `Blocked: ${blockerText}`)
        ]);
      }

      // Surface validation warnings as warning messages (C2)
      if (val && val.warnings && val.warnings.length > 0) {
        const warnText = val.warnings.map((w) => w.message).join('\n');
        setMessages((prev) => [...prev,
          msg('warning', `Warning: ${warnText}`)
        ]);
      }

      if (data.preview_url) {
        setPreviewUrls((prev) => ({ ...prev, edited: data.preview_url }));
      }
    } catch (err) {
      setError(err.message);
      setMessages((prev) => [...prev, msg('error', `Error: ${err.message}`)]);
    } finally {
      setLoading(false);
      setLoadingStartTime(null);
    }
  }, [sessionId]);

  const retryLastAi = useCallback((messageId) => {
    // Remove the AI message (and any validation messages after it) then re-send
    if (!lastPromptRef.current) return;
    const prompt = lastPromptRef.current;

    setMessages((prev) => {
      // Find the message to retry and remove it + everything after it
      const idx = prev.findIndex((m) => m.id === messageId);
      if (idx === -1) return prev;
      // Also remove the user message right before it
      const userIdx = idx - 1;
      if (userIdx >= 0 && prev[userIdx].role === 'user') {
        return prev.slice(0, userIdx);
      }
      return prev.slice(0, idx);
    });

    // Re-send after state update
    setTimeout(() => sendPrompt(prompt), 0);
  }, [sendPrompt]);

  const toggleOp = useCallback((index) => {
    setSelectedOps((prev) =>
      prev.includes(index) ? prev.filter((i) => i !== index) : [...prev, index]
    );
  }, []);

  const apply = useCallback(async () => {
    if (!sessionId) return;
    const startTime = Date.now();
    setLoading(true);
    setLoadingStartTime(startTime);
    setError(null);
    try {
      const data = await applyChanges(sessionId, selectedOps);

      // Build detailed post-apply summary from results array (H1)
      let summaryText = data.message || 'Changes applied.';
      if (data.results && data.results.length > 0) {
        const details = data.results
          .map((r, i) => {
            const op = operations[selectedOps[i]];
            const desc = op ? (op.description || op.summary || op.op_type) : `Operation ${i + 1}`;
            return r.success ? `  ${desc}` : `  ${desc} (failed${r.message ? ': ' + r.message : ''})`;
          })
          .join('\n');
        summaryText += `\n${details}`;
      }

      setMessages((prev) => [...prev, msg('system', summaryText)]);

      try {
        const blob = await getRenderBlob(sessionId, 'edited');
        const url = URL.createObjectURL(blob);
        setPreviewUrls((prev) => ({ ...prev, edited: url }));
      } catch (renderErr) {
        console.warn('[cad] Edited render fetch failed:', renderErr.message);
        setMessages((prev) => [...prev,
          msg('system', 'Preview not available — download the edited DXF to view.'),
        ]);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      setLoadingStartTime(null);
    }
  }, [sessionId, selectedOps, operations]);

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
    lastPromptRef.current = null;
  }, [sessionId]);

  const compareRevision = useCallback(async (file, profile = null) => {
    if (!sessionId) return;
    setLoading(true);
    setLoadingStartTime(Date.now());
    setError(null);
    try {
      const data = await compareFiles(sessionId, file, profile);
      setComparisonResult(data);
      setMessages((prev) => [...prev,
        msg('system', `Comparison complete: ${data.total_changes} change(s) found — ${data.summary.added || 0} added, ${data.summary.removed || 0} removed, ${data.summary.modified || 0} modified, ${data.summary.moved || 0} moved.`),
      ]);

      // Fetch comparison render
      if (data.render_available) {
        try {
          const blob = await getRenderBlob(sessionId, 'comparison');
          const url = URL.createObjectURL(blob);
          setPreviewUrls((prev) => ({ ...prev, comparison: url }));
        } catch (renderErr) {
          console.warn('[cad] Comparison render fetch failed:', renderErr.message);
        }
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      setLoadingStartTime(null);
    }
  }, [sessionId]);

  const handleRevisionApply = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await revisionApply(sessionId);
      setRevisionApplyResult(data);
      setBundleReady(true);
      const failMsg = data.failure_count > 0 ? ` (${data.failure_count} failed)` : '';
      setMessages((prev) => [...prev,
        msg('system', `Applied ${data.success_count} revision change(s) successfully${failMsg}.`),
      ]);
    } catch (err) {
      setError(err.message);
      setMessages((prev) => [...prev, msg('error', `Apply failed: ${err.message}`)]);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  const handleBundleDownload = useCallback(() => {
    if (!sessionId) return;
    const url = revisionDownloadUrl(sessionId);
    const a = document.createElement('a');
    a.href = url;
    a.download = '';
    document.body.appendChild(a);
    a.click();
    a.remove();
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
    setPreviewUrls({ original: null, edited: null, comparison: null });
    setComparisonResult(null);
    setRevisionOps(null);
    setRevisionApplyResult(null);
    setBundleReady(false);
    setError(null);
    setLoadingStartTime(null);
    lastPromptRef.current = null;
  }, [previewUrls]);

  return {
    sessionId,
    fileInfo,
    messages,
    operations,
    selectedOps,
    validation,
    previewUrls,
    comparisonResult,
    loading,
    loadingStartTime,
    error,
    clearError,
    upload,
    sendPrompt,
    retryLastAi,
    toggleOp,
    apply,
    download,
    compareRevision,
    clearConversation,
    revisionOps,
    revisionApplyResult,
    bundleReady,
    handleRevisionApply,
    handleBundleDownload,
    reset,
  };
}
