// ── Server Connection ────────────────────────────────────────────────
export const WS_URL = 'ws://127.0.0.1:11711/ws';
export const API_URL = 'http://127.0.0.1:11711';

// ── App Info ─────────────────────────────────────────────────────────
export const APP_NAME = 'JARVIS Mark II';
export const APP_VERSION = '2.0.0';

// ── UI Constants ─────────────────────────────────────────────────────
export const TOPBAR_HEIGHT = 36;

// ── WebSocket Reconnect ──────────────────────────────────────────────
export const WS_RECONNECT_DELAY = 2000;
export const WS_MAX_RECONNECT_DELAY = 30000;
export const WS_HEARTBEAT_INTERVAL = 25000;

// ── Theme ────────────────────────────────────────────────────────────
export const THEMES = ['dark', 'midnight', 'cyber'];

// ── Reasoning Effort ──────────────────────────────────────────────────
// Options for the reasoning effort dropdown
export const REASONING_EFFORT_OPTIONS = [
  { value: '', label: 'Auto' },
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
];

/**
 * Strip common provider prefixes from a model ID string.
 * e.g. "openai/o1-mini" → "o1-mini", "google/gemini-2.0-flash-thinking" → "gemini-2.0-flash-thinking"
 */
export function stripProviderPrefix(model) {
  if (!model) return '';
  const name = model.trim();
  // If there's a '/', keep only the part after the last '/'
  if (name.includes('/')) {
    return name.split('/').pop();
  }
  return name;
}

/**
 * Check whether a model ID supports the `reasoning_effort` parameter.
 * Strips provider prefixes first, then matches against known patterns.
 */
export function supportsReasoningEffort(model) {
  if (!model) return false;
  const bare = stripProviderPrefix(model).toLowerCase();
  return REASONING_MODEL_PATTERNS.some((pattern) => pattern.test(bare));
}

// Model ID patterns (bare names, no provider prefix — stripped before matching)
export const REASONING_MODEL_PATTERNS = [
  // OpenAI reasoning models: o1, o3, o4-mini, and gpt-5 (any variant)
  /^o1/,          // o1, o1-mini, o1-preview
  /^o3/,          // o3, o3-mini
  /^o4/,          // o4, o4-mini
  // Google Gemini thinking models
  /^gemini.*flash-thinking/,
  /^gemini.*thinking/,
  // DeepSeek reasoning models
  /^deepseek-reasoner/,
  /^deepseek.*reason/,
  // xAI Grok models with effort dial (conservative: only known-good prefixes)
  /^grok-3-mini/,
  /^grok-4\.20-multi-agent/,
  /^grok-4\.3/,
];
