#!/usr/bin/env node
// @ts-check
/**
 * Scorecard generator + regression gate for realworld prompt E2E tests.
 *
 * Reads recorded response JSONs from test-results/realworld-responses/,
 * computes accuracy/quality/timing metrics, saves a scorecard snapshot,
 * and compares against previous runs to detect regressions.
 *
 * Exit code 1 on regression (blocks deploy).
 *
 * Usage:
 *   node web/frontend/e2e/realworld-report.js
 */

import { execSync } from 'child_process';
import fs from 'fs';
import path from 'path';

const PROJECT_ROOT = path.resolve(import.meta.dirname, '..', '..', '..');
const RESULTS_DIR = path.join(import.meta.dirname, '..', 'test-results', 'realworld-responses');
const HISTORY_DIR = path.join(import.meta.dirname, '..', 'test-results', 'scorecard-history');
const THRESHOLDS_PATH = path.join(import.meta.dirname, '..', 'realworld-thresholds.json');

function loadThresholds() {
  try {
    return JSON.parse(fs.readFileSync(THRESHOLDS_PATH, 'utf-8'));
  } catch {
    return { min_accuracy: 0.80, max_p95_ms: 30000, max_regression_pct: 5 };
  }
}

function loadResponses() {
  if (!fs.existsSync(RESULTS_DIR)) {
    console.error(`No results directory found at ${RESULTS_DIR}`);
    process.exit(1);
  }

  const files = fs.readdirSync(RESULTS_DIR).filter(f => f.endsWith('.json'));
  if (files.length === 0) {
    console.error('No response files found. Run the realworld tests first.');
    process.exit(1);
  }

  return files.map(f => JSON.parse(fs.readFileSync(path.join(RESULTS_DIR, f), 'utf-8')));
}

function loadPreviousScorecard() {
  if (!fs.existsSync(HISTORY_DIR)) return null;

  const files = fs.readdirSync(HISTORY_DIR)
    .filter(f => f.endsWith('.json'))
    .sort()
    .reverse();

  if (files.length === 0) return null;
  return JSON.parse(fs.readFileSync(path.join(HISTORY_DIR, files[0]), 'utf-8'));
}

function percentile(values, p) {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const idx = Math.ceil((p / 100) * sorted.length) - 1;
  return sorted[Math.max(0, idx)];
}

function buildScorecard(responses) {
  let passed = 0;
  let failed = 0;
  let skipped = 0;
  const failures = [];
  const timings = [];
  const byCategory = {};
  let qualitySum = 0;
  let qualityCount = 0;

  for (const r of responses) {
    const cat = r.category || 'unknown';
    if (!byCategory[cat]) {
      byCategory[cat] = { total: 0, passed: 0, quality_sum: 0, quality_count: 0 };
    }
    byCategory[cat].total++;

    if (r.skipped) {
      skipped++;
      continue;
    }

    const assertions = r.assertions || {};
    const allPass = assertions.no_crash && assertions.behavior_match;

    if (allPass) {
      passed++;
      byCategory[cat].passed++;
    } else {
      failed++;
      failures.push({
        id: r.prompt_id,
        category: cat,
        reason: !assertions.no_crash ? 'crash/500' : 'behavior mismatch',
        expected_behavior: r.expected_behavior,
        got_family: r.response?.task_family,
        got_ops: r.response?.operations?.length || 0,
      });
    }

    if (r.quality?.score != null) {
      qualitySum += r.quality.score;
      qualityCount++;
      byCategory[cat].quality_sum += r.quality.score;
      byCategory[cat].quality_count++;
    }

    if (r.duration_ms != null) {
      timings.push(r.duration_ms);
    }
  }

  const total = responses.length;
  const accuracy = total - skipped > 0 ? passed / (total - skipped) : 0;

  // Compute per-category quality averages
  const byCategoryFinal = {};
  for (const [cat, data] of Object.entries(byCategory)) {
    byCategoryFinal[cat] = {
      total: data.total,
      passed: data.passed,
      quality_avg: data.quality_count > 0
        ? Math.round((data.quality_sum / data.quality_count) * 1000) / 1000
        : null,
    };
  }

  let gitSha = '';
  try {
    gitSha = execSync('git rev-parse --short HEAD', { encoding: 'utf-8', cwd: PROJECT_ROOT }).trim();
  } catch {
    // ignore
  }

  return {
    run_id: new Date().toISOString(),
    git_sha: gitSha,
    provider: 'gemini',
    total,
    passed,
    failed,
    skipped,
    accuracy: Math.round(accuracy * 1000) / 1000,
    quality_avg: qualityCount > 0
      ? Math.round((qualitySum / qualityCount) * 1000) / 1000
      : null,
    timing: {
      avg_ms: timings.length > 0 ? Math.round(timings.reduce((a, b) => a + b, 0) / timings.length) : 0,
      p50_ms: percentile(timings, 50),
      p95_ms: percentile(timings, 95),
    },
    by_category: byCategoryFinal,
    failures,
  };
}

function checkRegression(current, previous, thresholds) {
  const issues = [];
  let hasFailure = false;

  // Absolute minimum accuracy
  if (current.accuracy < thresholds.min_accuracy) {
    issues.push(`FAIL: Accuracy ${(current.accuracy * 100).toFixed(1)}% below minimum ${(thresholds.min_accuracy * 100).toFixed(1)}%`);
    hasFailure = true;
  }

  // p95 latency
  if (current.timing.p95_ms > thresholds.max_p95_ms) {
    issues.push(`WARN: p95 latency ${current.timing.p95_ms}ms exceeds max ${thresholds.max_p95_ms}ms`);
  }

  if (previous) {
    // Accuracy regression
    const accuracyDrop = (previous.accuracy - current.accuracy) * 100;
    if (accuracyDrop > thresholds.max_regression_pct) {
      issues.push(
        `FAIL: Accuracy dropped ${accuracyDrop.toFixed(1)}% ` +
        `(${(previous.accuracy * 100).toFixed(1)}% → ${(current.accuracy * 100).toFixed(1)}%), ` +
        `max allowed regression is ${thresholds.max_regression_pct}%`
      );
      hasFailure = true;
    }

    // p95 latency doubled
    if (previous.timing.p95_ms > 0 && current.timing.p95_ms > previous.timing.p95_ms * 2) {
      issues.push(
        `WARN: p95 latency doubled (${previous.timing.p95_ms}ms → ${current.timing.p95_ms}ms)`
      );
    }

    // New failures (passed before, fail now)
    if (previous.failures && current.failures) {
      const prevFailIds = new Set(previous.failures.map(f => f.id));
      const newFailures = current.failures.filter(f => !prevFailIds.has(f.id));
      if (newFailures.length > 0) {
        issues.push(
          `WARN: ${newFailures.length} new failure(s): ${newFailures.map(f => f.id).join(', ')}`
        );
      }
    }
  }

  return { issues, hasFailure };
}

// ── Main ──

const responses = loadResponses();
const scorecard = buildScorecard(responses);
const thresholds = loadThresholds();
const previous = loadPreviousScorecard();

// Save scorecard
fs.mkdirSync(HISTORY_DIR, { recursive: true });
const filename = scorecard.run_id.replace(/[:.]/g, '-') + '.json';
fs.writeFileSync(
  path.join(HISTORY_DIR, filename),
  JSON.stringify(scorecard, null, 2) + '\n'
);

// Print report
console.log('\n══════════════════════════════════════════════════');
console.log('  REALWORLD PROMPT SCORECARD');
console.log('══════════════════════════════════════════════════\n');

console.log(`  Run:      ${scorecard.run_id}`);
console.log(`  Git SHA:  ${scorecard.git_sha}`);
console.log(`  Provider: ${scorecard.provider}\n`);

console.log(`  Total:    ${scorecard.total}`);
console.log(`  Passed:   ${scorecard.passed}`);
console.log(`  Failed:   ${scorecard.failed}`);
console.log(`  Skipped:  ${scorecard.skipped}`);
console.log(`  Accuracy: ${(scorecard.accuracy * 100).toFixed(1)}%`);
if (scorecard.quality_avg != null) {
  console.log(`  Quality:  ${(scorecard.quality_avg * 100).toFixed(1)}%`);
}
console.log(`\n  Timing:   avg=${scorecard.timing.avg_ms}ms  p50=${scorecard.timing.p50_ms}ms  p95=${scorecard.timing.p95_ms}ms\n`);

console.log('  By Category:');
for (const [cat, data] of Object.entries(scorecard.by_category)) {
  const qStr = data.quality_avg != null ? `  quality=${(data.quality_avg * 100).toFixed(0)}%` : '';
  console.log(`    ${cat.padEnd(22)} ${data.passed}/${data.total} passed${qStr}`);
}

if (scorecard.failures.length > 0) {
  console.log('\n  Failures:');
  for (const f of scorecard.failures) {
    console.log(`    ${f.id}: ${f.reason} (expected=${f.expected_behavior}, got_family=${f.got_family}, ops=${f.got_ops})`);
  }
}

// Check regression
const regression = checkRegression(scorecard, previous, thresholds);
if (regression.issues.length > 0) {
  console.log('\n  Regression Analysis:');
  for (const issue of regression.issues) {
    console.log(`    ${issue}`);
  }
}

if (previous) {
  console.log(`\n  Previous: ${previous.run_id} (accuracy=${(previous.accuracy * 100).toFixed(1)}%)`);
}

console.log('\n══════════════════════════════════════════════════\n');
console.log(`  Scorecard saved: ${filename}`);
console.log('');

if (regression.hasFailure) {
  console.error('REGRESSION DETECTED — exiting with code 1');
  process.exit(1);
}

console.log('No regressions detected.');
