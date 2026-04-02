import { useState, useCallback, useRef } from 'react';
import {
  uploadFile, planEdit, v2Prompt, applyChanges, downloadFile, getRenderBlob, getDxfBlob,
  clearHistory, compareFiles, revisionUpload, revisionAlign, revisionDiff,
  revisionApprove, revisionApply, revisionDownloadBlob,
  v2Preview, v2Approve, v2Apply,
} from '../lib/api';


const NO_CHANGES_MESSAGE = "I couldn't plan any changes. Try being more specific about which element to edit.";

/** Create a message object with a unique ID and timestamp */
function msg(role, text, extra = {}) {
  return { id: crypto.randomUUID(), role, text, ts: Date.now(), ...extra };
}

/** Revoke a blob URL if it exists, preventing memory leaks. */
function revokeIfBlob(url) {
  if (url && url.startsWith('blob:')) URL.revokeObjectURL(url);
}

export function useSession() {
  const [sessionId, setSessionId] = useState(null);
  const [documentId, setDocumentId] = useState(null);
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

  // Structured edit plan preview/apply state (EPIC-CAD-08)
  const [editPreview, setEditPreview] = useState(null);
  const [editApproval, setEditApproval] = useState(null);
  const [editApplyResult, setEditApplyResult] = useState(null);
  const [currentPlanId, setCurrentPlanId] = useState(null);

  // Precision controls state (EPIC-CAD-14)
  const [precisionControls, setPrecisionControls] = useState(null);
  const [ambiguityCandidates, setAmbiguityCandidates] = useState([]);
  const [precisionActions, setPrecisionActions] = useState([]);

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
      setFileInfo({ ...data.file_info, page_classifications: data.page_classifications || null });
      // Fetch PNG render and DXF blob in parallel
      const [renderResult, dxfResult] = await Promise.allSettled([
        getRenderBlob(data.session_id, 'original'),
        getDxfBlob(data.session_id, 'original'),
      ]);
      if (renderResult.status === 'fulfilled') {
        setPreviewUrls((prev) => {
          revokeIfBlob(prev.original);
          return { ...prev, original: URL.createObjectURL(renderResult.value) };
        });
      } else {
        console.warn('[cad] Original render fetch failed:', renderResult.reason?.message);
      }
      if (dxfResult.status === 'fulfilled') {
        setDxfUrls((prev) => {
          revokeIfBlob(prev.original);
          return { ...prev, original: URL.createObjectURL(dxfResult.value) };
        });
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

  const sendPrompt = useCallback(async (prompt, selectedRegions = null) => {
    if (!sessionId) return;
    const startTime = Date.now();
    setLoading(true);
    setLoadingStartTime(startTime);
    setError(null);
    lastPromptRef.current = prompt;
    setMessages((prev) => [...prev, msg('user', prompt)]);

    try {
      // Build client metadata from precision controls if set (EPIC-CAD-14)
      const clientMetadata = precisionControls ? precisionControls : null;

      // Route through v2 endpoint first for intent classification
      const v2Data = await v2Prompt(sessionId, prompt, selectedRegions, clientMetadata);
      const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);

      // Extract precision-specific response data (EPIC-CAD-14)
      if (v2Data.ambiguity_candidates) setAmbiguityCandidates(v2Data.ambiguity_candidates);
      if (v2Data.precision_actions) setPrecisionActions(v2Data.precision_actions);

      // Handle Q&A responses directly (no operations)
      if (v2Data.response_type === 'answer_only' || v2Data.task_family === 'qna') {
        setOperations([]);
        setSelectedOps([]);
        setValidation(null);
        setMessages((prev) => [...prev, msg('ai', v2Data.message, { elapsed, qnaData: v2Data })]);
        return;
      }

      // Handle needs_clarification from v2
      if (v2Data.response_type === 'needs_clarification') {
        setOperations([]);
        setSelectedOps([]);
        setValidation(null);
        setMessages((prev) => [...prev, msg('ai', v2Data.message, { elapsed })]);
        return;
      }

      // Handle unsupported_operation from v2
      if (v2Data.response_type === 'unsupported_operation') {
        setOperations([]);
        setSelectedOps([]);
        setValidation(null);
        setMessages((prev) => [...prev, msg('ai', v2Data.message, { elapsed })]);
        return;
      }

      // For edit_plan: v2 returns plan_only — use v2 response directly
      const data = v2Data;
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
  }, [sessionId, precisionControls]);

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
        setPreviewUrls((prev) => {
          revokeIfBlob(prev.edited);
          return { ...prev, edited: URL.createObjectURL(renderRes.value) };
        });
      } else {
        console.warn('[cad] Edited render fetch failed:', renderRes.reason?.message);
        setMessages((prev) => [...prev,
          msg('system', 'Preview not available — download the edited DXF to view.'),
        ]);
      }
      if (dxfRes.status === 'fulfilled') {
        setDxfUrls((prev) => {
          revokeIfBlob(prev.edited);
          return { ...prev, edited: URL.createObjectURL(dxfRes.value) };
        });
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
          setPreviewUrls((prev) => {
            revokeIfBlob(prev.comparison);
            return { ...prev, comparison: URL.createObjectURL(blob) };
          });
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
        setDxfUrls((prev) => {
          revokeIfBlob(prev.comparison);
          return { ...prev, comparison: URL.createObjectURL(compBlob) };
        });
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

  const handleRealign = useCallback(async (controlPointStrings) => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const alignData = await revisionAlign(sessionId, controlPointStrings);
      setAlignmentResult(alignData);
      setMessages((prev) => [...prev,
        msg('system', `Re-aligned with ${controlPointStrings.length} control point(s): ${alignData.method} (${(alignData.confidence * 100).toFixed(0)}% confidence)`),
      ]);

      // Re-run diff with new alignment
      const diffData = await revisionDiff(sessionId);
      setComparisonResult(diffData);
      setRevisionOps(diffData.ops || []);
      setDiffSummary(diffData.diff_summary || null);

      // Re-fetch comparison DXF
      try {
        const compBlob = await getDxfBlob(sessionId, 'comparison');
        setDxfUrls((prev) => {
          if (prev.comparison) URL.revokeObjectURL(prev.comparison);
          return { ...prev, comparison: URL.createObjectURL(compBlob) };
        });
      } catch (dxfErr) {
        console.warn('[cad] Comparison DXF re-fetch failed:', dxfErr.message);
      }
    } catch (err) {
      setError(err.message);
      setMessages((prev) => [...prev, msg('error', `Re-alignment failed: ${err.message}`)]);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  const handleBundleDownload = useCallback(async () => {
    if (!sessionId) return;
    try {
      const blob = await revisionDownloadBlob(sessionId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'revision_bundle.zip';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message);
    }
  }, [sessionId]);

  // --- Structured edit plan preview/approve/apply (EPIC-CAD-08) ---

  const previewPlan = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await v2Preview(sessionId);
      setEditPreview(data);
      if (data.data?.plan_id) setCurrentPlanId(data.data.plan_id);
      setMessages((prev) => [...prev, msg('system', `Preview ready: ${data.data?.total_actions || 0} action(s)`)]);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  const approvePlan = useCallback(async (approved, notes = '') => {
    if (!sessionId || !currentPlanId) return;
    setError(null);
    try {
      const data = await v2Approve(sessionId, currentPlanId, approved, notes);
      setEditApproval(data);
      setMessages((prev) => [...prev, msg('system', approved ? 'Plan approved.' : 'Plan rejected.')]);
    } catch (err) {
      setError(err.message);
    }
  }, [sessionId, currentPlanId]);

  const approveAndApplyPlan = useCallback(async (notes = '') => {
    if (!sessionId || !currentPlanId) return;
    setLoading(true);
    setError(null);
    try {
      await v2Approve(sessionId, currentPlanId, true, notes);
      setEditApproval({ approved: true, plan_id: currentPlanId });
      setMessages((prev) => [...prev, msg('system', 'Plan approved.')]);

      const data = await v2Apply(sessionId);
      setEditApplyResult(data);
      const status = data.data?.status || 'unknown';
      const successCount = data.data?.success_count || 0;
      const failCount = data.data?.failure_count || 0;
      setMessages((prev) => [...prev, msg('system', `Apply ${status}: ${successCount} succeeded, ${failCount} failed`)]);

      const [renderRes, dxfRes] = await Promise.allSettled([
        getRenderBlob(sessionId, 'edited'),
        getDxfBlob(sessionId, 'edited'),
      ]);
      if (renderRes.status === 'fulfilled') {
        setPreviewUrls((prev) => {
          revokeIfBlob(prev.edited);
          return { ...prev, edited: URL.createObjectURL(renderRes.value) };
        });
      }
      if (dxfRes.status === 'fulfilled') {
        setDxfUrls((prev) => {
          revokeIfBlob(prev.edited);
          return { ...prev, edited: URL.createObjectURL(dxfRes.value) };
        });
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [sessionId, currentPlanId]);

  const applyPlan = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await v2Apply(sessionId);
      setEditApplyResult(data);
      const status = data.data?.status || 'unknown';
      const successCount = data.data?.success_count || 0;
      const failCount = data.data?.failure_count || 0;
      setMessages((prev) => [...prev, msg('system', `Apply ${status}: ${successCount} succeeded, ${failCount} failed`)]);

      // Fetch edited render and DXF
      const [renderRes, dxfRes] = await Promise.allSettled([
        getRenderBlob(sessionId, 'edited'),
        getDxfBlob(sessionId, 'edited'),
      ]);
      if (renderRes.status === 'fulfilled') {
        setPreviewUrls((prev) => {
          revokeIfBlob(prev.edited);
          return { ...prev, edited: URL.createObjectURL(renderRes.value) };
        });
      }
      if (dxfRes.status === 'fulfilled') {
        setDxfUrls((prev) => {
          revokeIfBlob(prev.edited);
          return { ...prev, edited: URL.createObjectURL(dxfRes.value) };
        });
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  /**
   * Hydrate session state from a library load response.
   * Called when a document is loaded from the document library.
   * The backend returns a session_id and file_info just like /api/upload,
   * so we reuse the same fetch pattern.
   */
  const loadFromLibraryData = useCallback(async (data, docId) => {
    setLoading(true);
    setLoadingStartTime(Date.now());
    setError(null);
    try {
      setDocumentId(docId);
      setSessionId(data.session_id);
      setFileInfo({ ...data.file_info, page_classifications: data.page_classifications || null });

      const [renderResult, dxfResult] = await Promise.allSettled([
        getRenderBlob(data.session_id, 'original'),
        getDxfBlob(data.session_id, 'original'),
      ]);
      if (renderResult.status === 'fulfilled') {
        setPreviewUrls((prev) => {
          revokeIfBlob(prev.original);
          return { ...prev, original: URL.createObjectURL(renderResult.value) };
        });
      } else {
        console.warn('[cad] Library load render fetch failed:', renderResult.reason?.message);
      }
      if (dxfResult.status === 'fulfilled') {
        setDxfUrls((prev) => {
          revokeIfBlob(prev.original);
          return { ...prev, original: URL.createObjectURL(dxfResult.value) };
        });
      } else {
        console.warn('[cad] Library load DXF fetch failed:', dxfResult.reason?.message);
      }

      const filename = data.file_info?.filename || 'document';
      setMessages([
        msg('system', `Loaded ${filename} (${data.file_info?.entity_count ?? '?'} entities, ${data.file_info?.layer_count ?? '?'} layers) from library`),
      ]);
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

  const reset = useCallback(() => {
    // Revoke blob URLs to free memory
    Object.values(previewUrls).forEach((url) => {
      if (url) URL.revokeObjectURL(url);
    });
    Object.values(dxfUrls).forEach((url) => {
      if (url) URL.revokeObjectURL(url);
    });
    setSessionId(null);
    setDocumentId(null);
    localStorage.removeItem('intentcad_active_document_id');
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
    setEditPreview(null);
    setEditApproval(null);
    setEditApplyResult(null);
    setCurrentPlanId(null);
    setPrecisionControls(null);
    setAmbiguityCandidates([]);
    setPrecisionActions([]);
    lastPromptRef.current = null;
  }, [previewUrls, dxfUrls]);

  return {
    sessionId,
    documentId,
    setDocumentId,
    loadFromLibraryData,
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
    handleRealign,
    editPreview,
    editApproval,
    editApplyResult,
    currentPlanId,
    previewPlan,
    approvePlan,
    approveAndApplyPlan,
    applyPlan,
    precisionControls,
    setPrecisionControls,
    ambiguityCandidates,
    precisionActions,
    reset,
  };
}
