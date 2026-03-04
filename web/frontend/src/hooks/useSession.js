import { useState, useCallback, useRef } from 'react';
import {
  uploadFile, planEdit, applyChanges, downloadFile, getRenderBlob, getDxfBlob,
  clearHistory, compareFiles, revisionUpload, revisionAlign, revisionDiff,
  revisionApprove, revisionApply, revisionDownloadUrl,
} from '../lib/api';

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
  const [dxfUrls, setDxfUrls] = useState({ original: null, edited: null, comparison: null });
  const [comparisonResult, setComparisonResult] = useState(null);
  const [revisionOps, setRevisionOps] = useState(null);
  const [revisionApplyResult, setRevisionApplyResult] = useState(null);
  const [bundleReady, setBundleReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingStartTime, setLoadingStartTime] = useState(null);
  const [error, setError] = useState(null);

  // Revision pipeline state
  const [revisionFile, setRevisionFile] = useState(null);
  const [alignmentResult, setAlignmentResult] = useState(null);
  const [diffSummary, setDiffSummary] = useState(null);
  const [wizardStep, setWizardStep] = useState(1);

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
      // Fetch PNG render and DXF blob in parallel
      const [renderResult, dxfResult] = await Promise.allSettled([
        getRenderBlob(data.session_id, 'original'),
        getDxfBlob(data.session_id, 'original'),
      ]);
      if (renderResult.status === 'fulfilled') {
        setPreviewUrls((prev) => ({ ...prev, original: URL.createObjectURL(renderResult.value) }));
      } else {
        console.warn('[cad] Original render fetch failed:', renderResult.reason?.message);
      }
      if (dxfResult.status === 'fulfilled') {
        setDxfUrls((prev) => ({ ...prev, original: URL.createObjectURL(dxfResult.value) }));
      } else {
        console.warn('[cad] Original DXF fetch failed:', dxfResult.reason?.message);
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

      // Fetch PNG render and DXF blob in parallel
      const [renderRes, dxfRes] = await Promise.allSettled([
        getRenderBlob(sessionId, 'edited'),
        getDxfBlob(sessionId, 'edited'),
      ]);
      if (renderRes.status === 'fulfilled') {
        setPreviewUrls((prev) => ({ ...prev, edited: URL.createObjectURL(renderRes.value) }));
      } else {
        console.warn('[cad] Edited render fetch failed:', renderRes.reason?.message);
        setMessages((prev) => [...prev,
          msg('system', 'Preview not available — download the edited DXF to view.'),
        ]);
      }
      if (dxfRes.status === 'fulfilled') {
        setDxfUrls((prev) => ({ ...prev, edited: URL.createObjectURL(dxfRes.value) }));
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

  // --- Revision pipeline handlers (wizard flow) ---

  const handleRevisionUpload = useCallback(async (file, profile = null) => {
    if (!sessionId) return;
    setLoading(true);
    setLoadingStartTime(Date.now());
    setError(null);
    setRevisionFile(file.name);
    try {
      await revisionUpload(sessionId, file);
      setMessages((prev) => [...prev,
        msg('system', `Revision file uploaded: ${file.name}`),
      ]);

      // Auto-run alignment
      const alignData = await revisionAlign(sessionId);
      setAlignmentResult(alignData);
      setWizardStep(2);
      setMessages((prev) => [...prev,
        msg('system', `Alignment: ${alignData.method} (${(alignData.confidence * 100).toFixed(0)}% confidence)`),
      ]);

      // Auto-run diff with profile
      const diffData = await revisionDiff(sessionId, profile);
      setComparisonResult(diffData);
      setRevisionOps(diffData.ops || []);
      setDiffSummary(diffData.diff_summary || null);
      setWizardStep(3);
      setMessages((prev) => [...prev,
        msg('system', diffData.diff_summary?.headline || `${diffData.total_changes} change(s) found`),
      ]);

      // Fetch comparison DXF for interactive viewer
      try {
        const compBlob = await getDxfBlob(sessionId, 'comparison');
        setDxfUrls((prev) => ({ ...prev, comparison: URL.createObjectURL(compBlob) }));
      } catch (dxfErr) {
        console.warn('[cad] Comparison DXF fetch failed:', dxfErr.message);
      }

      // Show warnings
      if (diffData.warnings && diffData.warnings.length > 0) {
        setMessages((prev) => [...prev,
          msg('warning', diffData.warnings.join('\n')),
        ]);
      }
      if (diffData.diff_summary?.warnings?.length > 0) {
        setMessages((prev) => [...prev,
          msg('warning', diffData.diff_summary.warnings.join('\n')),
        ]);
      }
    } catch (err) {
      setError(err.message);
      setMessages((prev) => [...prev, msg('error', `Revision failed: ${err.message}`)]);
    } finally {
      setLoading(false);
      setLoadingStartTime(null);
    }
  }, [sessionId]);

  const handleRevisionApproveOp = useCallback(async (opId, action) => {
    if (!sessionId) return;
    setError(null);
    try {
      const data = await revisionApprove(sessionId, [{ op_id: opId, action }]);
      // Update local ops state
      setRevisionOps((prev) =>
        prev.map((op) => {
          const updated = data.ops.find((d) => d.op_id === op.op_id);
          return updated ? { ...op, status: updated.status } : op;
        })
      );
    } catch (err) {
      setError(err.message);
    }
  }, [sessionId]);

  const handleRevisionBulkApprove = useCallback(async (action) => {
    if (!sessionId || !revisionOps) return;
    setError(null);
    try {
      const approvals = revisionOps
        .filter((op) => op.status === 'pending' || op.status === 'auto_approved' || (action === 'reject' && op.status !== 'rejected'))
        .map((op) => ({ op_id: op.op_id, action }));
      if (approvals.length === 0) return;
      const data = await revisionApprove(sessionId, approvals);
      setRevisionOps((prev) =>
        prev.map((op) => {
          const updated = data.ops.find((d) => d.op_id === op.op_id);
          return updated ? { ...op, status: updated.status } : op;
        })
      );
    } catch (err) {
      setError(err.message);
    }
  }, [sessionId, revisionOps]);

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
    Object.values(dxfUrls).forEach((url) => {
      if (url) URL.revokeObjectURL(url);
    });
    setSessionId(null);
    setFileInfo(null);
    setMessages([]);
    setOperations([]);
    setSelectedOps([]);
    setValidation(null);
    setPreviewUrls({ original: null, edited: null, comparison: null });
    setDxfUrls({ original: null, edited: null, comparison: null });
    setComparisonResult(null);
    setRevisionOps(null);
    setRevisionApplyResult(null);
    setBundleReady(false);
    setError(null);
    setLoadingStartTime(null);
    setRevisionFile(null);
    setAlignmentResult(null);
    setDiffSummary(null);
    setWizardStep(1);
    lastPromptRef.current = null;
  }, [previewUrls, dxfUrls]);

  return {
    sessionId,
    fileInfo,
    messages,
    operations,
    selectedOps,
    validation,
    previewUrls,
    dxfUrls,
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
    revisionFile,
    alignmentResult,
    diffSummary,
    wizardStep,
    revisionApplyResult,
    bundleReady,
    handleRevisionUpload,
    handleRevisionApproveOp,
    handleRevisionBulkApprove,
    handleRevisionApply,
    handleBundleDownload,
    reset,
  };
}
