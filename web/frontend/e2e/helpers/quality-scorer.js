// @ts-check
/**
 * Automated quality scoring module for the realworld E2E test suite.
 *
 * Scores each prompt/response pair on a 0.0–1.0 scale using category-specific
 * rubrics drawn from the realworld_prompts.json fixture categories. Designed
 * for use in batch E2E runs where you want a numeric signal per prompt without
 * hand-rolling assertions for 118+ cases.
 *
 * No external dependencies — pure Node.js / ES module.
 */

/**
 * Known facts about each drawing fixture. Used by qna/summary scorers to
 * check whether the response references drawing-specific vocabulary.
 *
 * @type {Record<string, DrawingFacts>}
 */
export const DRAWING_FACTS = {
  structural: {
    layers: ['STRUCTURAL', 'GRID', 'NOTES', 'DIMENSIONS', 'TITLE', 'TITLEBLOCK'],
    entity_types: ['INSERT', 'TEXT', 'MTEXT', 'LINE', 'LWPOLYLINE'],
    has_columns: true,
    has_text: true,
    has_dimensions: true,
  },
};

// ---------------------------------------------------------------------------
// Type definitions (JSDoc only — no runtime overhead)
// ---------------------------------------------------------------------------

/**
 * @typedef {Object} DrawingFacts
 * @property {string[]} layers - Layer names present in the drawing fixture.
 * @property {string[]} entity_types - DXF entity type strings found in the drawing.
 * @property {boolean} has_columns - True when the drawing contains column marks.
 * @property {boolean} has_text - True when the drawing contains text entities.
 * @property {boolean} has_dimensions - True when the drawing contains dimension lines.
 */

/**
 * Shape of a single entry from realworld_prompts.json.
 *
 * @typedef {Object} PromptDef
 * @property {string} id - Unique prompt identifier (e.g. "rw-move-001").
 * @property {string} category - Rubric category (e.g. "move", "qna", "summary").
 * @property {string} [subcategory] - Optional subcategory for finer grouping.
 * @property {string} prompt - The raw user prompt text.
 * @property {string} drawing_fixture - Key into DRAWING_FACTS (e.g. "structural").
 * @property {string} expected_family - Expected TaskFamily value.
 * @property {string} expected_behavior - One of: "produces_ops", "answer_only",
 *   "report", "needs_clarification", "blocked_by_validator", "no_ops".
 * @property {string[]} expected_op_types - Op type strings expected in the response
 *   (e.g. ["move_entity"]). May be empty for non-edit prompts.
 * @property {number} min_ops - Minimum acceptable operation count.
 * @property {boolean} must_not_produce_ops - True when ops are forbidden.
 * @property {string[]} [tags] - Arbitrary tag strings.
 */

/**
 * Shape of a single operation object as returned by /api/plan.
 *
 * @typedef {Object} PlanOperation
 * @property {string} op_type - Operation type value (e.g. "move_entity").
 * @property {string|null} [target_handle] - DXF entity handle, if applicable.
 * @property {string|null} [target_layer] - Layer the op targets.
 * @property {string} [description] - Human-readable description.
 * @property {Record<string, unknown>} [params] - Arbitrary op parameters.
 */

/**
 * Validation sub-object on a /api/plan response.
 *
 * @typedef {Object} PlanValidation
 * @property {{ message: string }[]} blockers - Blocking validation findings.
 * @property {{ message: string }[]} warnings - Non-blocking warnings.
 * @property {boolean} is_valid - False when any blockers exist.
 */

/**
 * Shape of a /api/plan API response (or equivalent test double).
 *
 * @typedef {Object} PlanResponse
 * @property {PlanOperation[]} [operations] - Planned operations (may be empty array).
 * @property {string} [summary] - Human-readable summary of the plan.
 * @property {string|null} [message] - LLM message when no ops were produced.
 * @property {PlanValidation} [validation] - Validation result.
 * @property {boolean} [crashed] - Set to true by test harness on unhandled exceptions.
 */

/**
 * Score breakdown for a single scored response.
 *
 * @typedef {Object} ScoreBreakdown
 * @property {number} base - Base score (0 or 0.5) for the minimum viable signal.
 * @property {number} type_match - Bonus (0 or 0.25) for op type / content match.
 * @property {number} content - Bonus (0 or 0.25) for richer content quality.
 */

/**
 * Return value of scoreResponse().
 *
 * @typedef {Object} ScoreResult
 * @property {number} score - Final score in [0.0, 1.0].
 * @property {ScoreBreakdown} breakdown - Additive components that sum to score.
 */

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * Safely extract the operations array from a response.
 *
 * @param {PlanResponse} response
 * @returns {PlanOperation[]}
 */
function getOps(response) {
  return Array.isArray(response.operations) ? response.operations : [];
}

/**
 * Returns true when the response message is a non-empty string.
 *
 * @param {PlanResponse} response
 * @returns {boolean}
 */
function hasMessage(response) {
  return typeof response.message === 'string' && response.message.length > 0;
}

/**
 * Checks whether the response message mentions at least one term from a list.
 * The check is case-insensitive.
 *
 * @param {string|null|undefined} message
 * @param {string[]} terms
 * @returns {boolean}
 */
function mentionsAny(message, terms) {
  if (!message) return false;
  const lower = message.toLowerCase();
  return terms.some((t) => lower.includes(t.toLowerCase()));
}

// ---------------------------------------------------------------------------
// Category-specific scorers
// ---------------------------------------------------------------------------

/**
 * Edit rubric — applies to all categories that expect DXF operations:
 *   move, delete, text (edit_text), create (add_block/add_*), transform
 *   (rotate, copy, scale, mirror), batch, multi_op, and spatial.
 *
 * @param {PromptDef} promptDef
 * @param {PlanResponse} response
 * @returns {ScoreResult}
 */
function scoreEdit(promptDef, response) {
  const ops = getOps(response);
  const hasOps = ops.length >= 1;

  /** @type {ScoreBreakdown} */
  const breakdown = { base: 0, type_match: 0, content: 0 };

  // 0.5 — ops produced
  if (hasOps) {
    breakdown.base = 0.5;
  }

  // +0.25 — op types match expected
  const expectedTypes = promptDef.expected_op_types ?? [];
  if (hasOps && expectedTypes.length > 0) {
    const producedTypes = new Set(ops.map((o) => o.op_type));
    const allMatch = expectedTypes.every((t) => producedTypes.has(t));
    if (allMatch) {
      breakdown.type_match = 0.25;
    }
  } else if (hasOps && expectedTypes.length === 0) {
    // No specific types expected — award the bonus by default
    breakdown.type_match = 0.25;
  }

  // +0.25 — op count meets minimum
  const minOps = promptDef.min_ops ?? 1;
  if (ops.length >= minOps) {
    breakdown.content = 0.25;
  }

  const score = Math.min(1.0, breakdown.base + breakdown.type_match + breakdown.content);
  return { score, breakdown };
}

/**
 * Q&A / query rubric — expects a substantive text answer, no ops.
 *
 * @param {PromptDef} promptDef
 * @param {PlanResponse} response
 * @returns {ScoreResult}
 */
function scoreQna(promptDef, response) {
  const msg = response.message ?? response.summary ?? '';
  const nonEmpty = typeof msg === 'string' && msg.length > 0;

  /** @type {ScoreBreakdown} */
  const breakdown = { base: 0, type_match: 0, content: 0 };

  // 0.5 — non-empty message
  if (nonEmpty) {
    breakdown.base = 0.5;
  }

  // +0.25 — mentions relevant layers or entity types from the drawing
  const fixture = promptDef.drawing_fixture ?? 'structural';
  const facts = DRAWING_FACTS[fixture] ?? DRAWING_FACTS.structural;
  const knownTerms = [...facts.layers, ...facts.entity_types];
  if (nonEmpty && mentionsAny(msg, knownTerms)) {
    breakdown.type_match = 0.25;
  }

  // +0.25 — substantive (>50 chars)
  if (nonEmpty && msg.length > 50) {
    breakdown.content = 0.25;
  }

  const score = Math.min(1.0, breakdown.base + breakdown.type_match + breakdown.content);
  return { score, breakdown };
}

/**
 * Summary rubric — expects a prose description mentioning layer and entity vocabulary.
 *
 * @param {PromptDef} promptDef
 * @param {PlanResponse} response
 * @returns {ScoreResult}
 */
function scoreSummary(promptDef, response) {
  const msg = response.message ?? response.summary ?? '';
  const nonEmpty = typeof msg === 'string' && msg.length > 0;

  /** @type {ScoreBreakdown} */
  const breakdown = { base: 0, type_match: 0, content: 0 };

  // 0.5 — non-empty message
  if (nonEmpty) {
    breakdown.base = 0.5;
  }

  const fixture = promptDef.drawing_fixture ?? 'structural';
  const facts = DRAWING_FACTS[fixture] ?? DRAWING_FACTS.structural;

  // +0.25 — mentions at least one layer name
  if (nonEmpty && mentionsAny(msg, facts.layers)) {
    breakdown.type_match = 0.25;
  }

  // +0.25 — mentions at least one entity type
  if (nonEmpty && mentionsAny(msg, facts.entity_types)) {
    breakdown.content = 0.25;
  }

  const score = Math.min(1.0, breakdown.base + breakdown.type_match + breakdown.content);
  return { score, breakdown };
}

/**
 * Needs-clarification rubric — the system should respond with a message but
 * produce zero operations. Produces ops is a failure.
 *
 * @param {PromptDef} _promptDef
 * @param {PlanResponse} response
 * @returns {ScoreResult}
 */
function scoreNeedsClarification(_promptDef, response) {
  const ops = getOps(response);
  const opsProduced = ops.length > 0;

  // Fail hard if ops were produced — this category requires no ops
  if (opsProduced) {
    return { score: 0.0, breakdown: { base: 0, type_match: 0, content: 0 } };
  }

  // Full score: no ops + has a clarifying message
  const hasMsg = hasMessage(response);
  const score = hasMsg ? 1.0 : 0.0;

  /** @type {ScoreBreakdown} */
  const breakdown = {
    base: hasMsg ? 0.5 : 0,
    type_match: hasMsg ? 0.25 : 0,
    content: hasMsg ? 0.25 : 0,
  };

  return { score, breakdown };
}

/**
 * Adversarial rubric — any prompt that attempts injection, XSS, or
 * destructive overreach. The system must not crash; it should route safely.
 * We do not penalise for producing ops (injection prompts often contain
 * real verbs like "delete"). We only penalise for crashes.
 *
 * @param {PromptDef} _promptDef
 * @param {PlanResponse} response
 * @returns {ScoreResult}
 */
function scoreAdversarial(_promptDef, response) {
  const crashed = response.crashed === true;

  // A crash is the only real failure mode here
  if (crashed) {
    return { score: 0.0, breakdown: { base: 0, type_match: 0, content: 0 } };
  }

  // No crash — full score
  return {
    score: 1.0,
    breakdown: { base: 0.5, type_match: 0.25, content: 0.25 },
  };
}

/**
 * Protected-layer rubric — prompts that target TITLE, TITLEBLOCK, SEAL, or
 * REVISION layers must be blocked by the validator.
 *
 * @param {PromptDef} _promptDef
 * @param {PlanResponse} response
 * @returns {ScoreResult}
 */
function scoreProtected(_promptDef, response) {
  const validation = response.validation;
  const blockers = validation?.blockers ?? [];
  const warnings = validation?.warnings ?? [];

  const hasBlocker = blockers.length > 0;
  const hasWarning = warnings.length > 0;

  if (hasBlocker) {
    // Ideal outcome: validator caught the protected-layer violation
    return {
      score: 1.0,
      breakdown: { base: 0.5, type_match: 0.25, content: 0.25 },
    };
  }

  if (hasWarning) {
    // Partial credit: warned but not hard-blocked
    return {
      score: 0.5,
      breakdown: { base: 0.5, type_match: 0, content: 0 },
    };
  }

  // No validation feedback at all — scorer treats this as a miss
  return { score: 0.0, breakdown: { base: 0, type_match: 0, content: 0 } };
}

// ---------------------------------------------------------------------------
// Category → scorer dispatch table
// ---------------------------------------------------------------------------

/**
 * Categories whose prompts expect DXF edit operations as output.
 * These all use the edit rubric regardless of their specific subcategory.
 */
const EDIT_CATEGORIES = new Set([
  'move',
  'delete',
  'text',
  'create',
  'transform',
  'batch',
  'multi_op',
  'spatial',
  // Aliases / alternate spellings that may appear in prompt fixtures
  'add_block',
  'add_entity',
  'rotate',
  'copy',
  'scale',
  'mirror',
  'edit_text',
]);

/**
 * Map from category string to a scorer function signature compatible with
 * the internal scorer interface.
 *
 * @type {Record<string, (pd: PromptDef, r: PlanResponse) => ScoreResult>}
 */
const CATEGORY_SCORERS = {
  // Edit operations
  move: scoreEdit,
  delete: scoreEdit,
  text: scoreEdit,
  create: scoreEdit,
  transform: scoreEdit,
  batch: scoreEdit,
  multi_op: scoreEdit,
  spatial: scoreEdit,
  add_block: scoreEdit,
  add_entity: scoreEdit,
  rotate: scoreEdit,
  copy: scoreEdit,
  scale: scoreEdit,
  mirror: scoreEdit,
  edit_text: scoreEdit,

  // Information retrieval
  qna: scoreQna,
  query: scoreQna,

  // Descriptive analysis
  summary: scoreSummary,
  health: scoreSummary,
  compliance: scoreSummary,
  takeoff: scoreSummary,
  rfi: scoreSummary,
  compare: scoreSummary,
  zone: scoreSummary,

  // Safety / edge cases
  needs_clarification: scoreNeedsClarification,
  adversarial: scoreAdversarial,
  protected: scoreProtected,

  // Prompt quality categories — use qna rubric as a reasonable proxy
  ambiguous: scoreQna,
  missing_ref: scoreQna,
  typo: scoreQna,
  jargon: scoreQna,
  language: scoreQna,
  context: scoreQna,
};

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Score a single prompt/response pair on a 0.0–1.0 scale.
 *
 * The score is determined by the prompt's `category` field. Unrecognised
 * categories fall back to the qna rubric (presence of a non-empty message).
 *
 * @param {PromptDef} promptDef - The prompt definition from realworld_prompts.json.
 * @param {PlanResponse} response - The API response (real or test double).
 * @returns {ScoreResult} Final score and additive breakdown.
 *
 * @example
 * const { score, breakdown } = scoreResponse(promptDef, apiResponse);
 * console.log(score);       // 0.75
 * console.log(breakdown);   // { base: 0.5, type_match: 0.25, content: 0 }
 */
export function scoreResponse(promptDef, response) {
  const category = (promptDef.category ?? '').toLowerCase();

  // expected_behavior can override the category-level scorer for edge cases.
  // If the prompt says "needs_clarification" regardless of category, use that rubric.
  const behavior = (promptDef.expected_behavior ?? '').toLowerCase();
  if (behavior === 'needs_clarification') {
    return scoreNeedsClarification(promptDef, response);
  }
  if (behavior === 'blocked_by_validator') {
    return scoreProtected(promptDef, response);
  }

  const scorer = CATEGORY_SCORERS[category] ?? scoreQna;
  return scorer(promptDef, response);
}
