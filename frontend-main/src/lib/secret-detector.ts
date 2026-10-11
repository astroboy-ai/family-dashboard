/**
 * Client-side secret detection for the Smart Text block.
 *
 * Why this exists
 * ---------------
 * A Smart Text block lets the user paste a messy page out of Notepad++ — a
 * mixture of ordinary lines and credentials — and keep it as one note instead
 * of hand-splitting it into a dozen password blocks. Detecting which lines are
 * credentials is the whole feature, and it has to happen **in the browser**:
 * the plaintext must never be sent anywhere to be classified, least of all to
 * an LLM or an embedding provider.
 *
 * So this module is deliberately local and deterministic. No network, no AI.
 *
 * Design
 * ------
 * Detection is layered, because no single signal is enough:
 *
 *   1. **Provider formats** (`ghp_…`, `xoxb-…`, `AIza…`, JWTs) — the format
 *      itself is meaningful, so confidence is very high.
 *   2. **Contextual labels** (`password:`, `api key:`, `robot key:`) — the label
 *      tells us a value follows and is probably secret.
 *   3. **Entropy** — only ever *raises* confidence on an existing match. A bare
 *      high-entropy string is not a finding; random-looking text is everywhere.
 *
 * Two rules keep the noise down, and both matter more than the patterns:
 *
 * - **Placeholders are skipped.** `<your-api-key>`, `${TOKEN}`, `YOUR_KEY`,
 *   `CHANGEME` — agents and docs produce these constantly and they are not
 *   secrets.
 * - **Overlapping matches are resolved by confidence.** `password: abc123` can
 *   match both the password rule and a generic assignment rule; the strongest
 *   one wins and the span is reported once.
 *
 * Nothing here is authoritative. A finding means "this might be a secret — you
 * decide", which is why the UI always asks before protecting anything.
 */

export type Severity = "CRITICAL" | "HIGH" | "MEDIUM";

export type Finding = {
  /** Stable across re-runs for the same span, so checkbox state survives. */
  id: string;
  /** Character offsets into the source text, half-open `[start, end)`. */
  start: number;
  end: number;
  /**
   * The matched text itself.
   *
   * Shown in the review list. Hiding it was the wrong call: the value is
   * already visible in the textarea the user just pasted into, so masking it
   * bought no secrecy and cost comprehension — worse on mobile, where the
   * review panel covers the text and the user cannot see which value matched.
   */
  value: string;
  /** Human label taken from the surrounding line, e.g. "google password". */
  label: string;
  /** Machine type, e.g. `password`, `github_token`. */
  type: string;
  severity: Severity;
  /** Rule confidence 0–1, before any entropy adjustment. */
  confidence: number;
  /** Shannon entropy of the matched value — shown for transparency. */
  entropy: number;
  /** Whether the value should be protected by default. */
  selected: boolean;
  /** True when the user marked this span by hand with `[[secret]]…[[/secret]]`. */
  manual?: boolean;
  /** Which rule produced it, for the "why was this flagged?" line. */
  rule?: string;
};

type Rule = {
  id: string;
  type: string;
  severity: Severity;
  confidence: number;
  regex: RegExp;
  /**
   * Which capture group holds the secret. Provider patterns match the whole
   * token, so they use group 0; contextual rules capture only the value.
   */
  valueGroup: number;
};

const SEVERITY_RANK: Record<Severity, number> = {
  CRITICAL: 3,
  HIGH: 2,
  MEDIUM: 1,
};

/**
 * Rules whose *format* proves what they are.
 *
 * These are versioned assumptions, not permanent truths — providers change
 * their token shapes — so they live at the top where they are easy to revise.
 */
const PROVIDER_RULES: Rule[] = [
  {
    id: "private_key",
    type: "private_key",
    severity: "CRITICAL",
    confidence: 0.999,
    // Only the header is matched. The body is base64 lines that would match a
    // generic rule anyway, and redacting the header is enough to identify it.
    regex: /-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----/g,
    valueGroup: 0,
  },
  {
    id: "github_pat_fine",
    type: "github_token",
    severity: "CRITICAL",
    confidence: 0.995,
    regex: /\bgithub_pat_[A-Za-z0-9_]{20,255}\b/g,
    valueGroup: 0,
  },
  {
    id: "github_pat",
    type: "github_token",
    severity: "CRITICAL",
    confidence: 0.995,
    regex: /\bgh[pousr]_[A-Za-z0-9]{20,255}\b/g,
    valueGroup: 0,
  },
  {
    id: "slack_token",
    type: "slack_token",
    severity: "CRITICAL",
    confidence: 0.995,
    regex: /\bxox[baprs]-[A-Za-z0-9-]{10,}\b/g,
    valueGroup: 0,
  },
  {
    id: "google_api_key",
    type: "google_api_key",
    severity: "HIGH",
    confidence: 0.98,
    regex: /\bAIza[A-Za-z0-9_-]{30,}\b/g,
    valueGroup: 0,
  },
  {
    id: "openai_key",
    type: "api_key",
    severity: "HIGH",
    confidence: 0.97,
    regex: /\bsk-[A-Za-z0-9_-]{20,}\b/g,
    valueGroup: 0,
  },
  {
    id: "jwt",
    type: "jwt",
    severity: "HIGH",
    confidence: 0.96,
    regex: /\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/g,
    valueGroup: 0,
  },
  {
    id: "connection_string",
    type: "database_credentials",
    severity: "CRITICAL",
    confidence: 0.98,
    // `user:password@host` — the whole authority section is the secret.
    regex: /\b(?:mongodb(?:\+srv)?|postgres(?:ql)?|mysql|mariadb|redis):\/\/[^\s/@]+:[^\s/@]+@/gi,
    valueGroup: 0,
  },
  {
    id: "bearer",
    type: "bearer_token",
    severity: "HIGH",
    confidence: 0.94,
    regex: /\bBearer\s+([A-Za-z0-9._~+/-]{20,}={0,2})/g,
    valueGroup: 1,
  },
];

/**
 * Rules driven by a label the user wrote.
 *
 * The label is what makes these work: `1234567` alone is meaningless, but
 * `google password: 1234567` is not. Group 1 is the label (kept as the
 * human-readable name), group 2 is the value.
 *
 * `[^\n]*?` rather than `.+?` so a match never runs across lines — a label with
 * no value on its line should not swallow the next one.
 *
 * The keyword boundary is `(?<![A-Za-z0-9])` / `(?![A-Za-z0-9])`, **not** `\b`.
 * Underscore is a word character, so `\bpassword\b` does not match inside
 * `DATABASE_PASSWORD` — the commonest shape of all. Treating `_` as a separator
 * lets SCREAMING_SNAKE env-var names match while still refusing `mypasswordx`.
 */
const CONTEXT_RULES: Rule[] = [
  {
    id: "password_assignment",
    type: "password",
    severity: "HIGH",
    confidence: 0.9,
    regex:
      /^([^\n:=]{0,60}?(?<![A-Za-z0-9])(?:password|passwd|pwd|passphrase)(?![A-Za-z0-9])[^\n:=]{0,40})[:=]\s*["'`]?([^\s"'`,;]{3,})["'`]?/gim,
    valueGroup: 2,
  },
  {
    id: "key_assignment",
    type: "api_key",
    severity: "HIGH",
    confidence: 0.85,
    regex:
      /^([^\n:=]{0,60}?(?<![A-Za-z0-9])(?:api[ _-]?key|access[ _-]?token|auth[ _-]?token|client[ _-]?secret|secret[ _-]?key|token|secret|key)(?![A-Za-z0-9])[^\n:=]{0,40})[:=]\s*["'`]?([^\s"'`,;]{8,})["'`]?/gim,
    valueGroup: 2,
  },
];

const ALL_RULES: Rule[] = [...PROVIDER_RULES, ...CONTEXT_RULES];

/**
 * A line that is only a label — `Orange system:` with nothing after the colon.
 *
 * This shape is how people actually write a credential block in a text file:
 * a heading, then one value per line. The inline rules above cannot see it,
 * because there is no `label: value` on any single line.
 */
const BARE_LABEL = /^[ \t]*([^\n:]{1,40}?)[ \t]*:[ \t]*$/;

/** Schemes that make a value a URL rather than a credential. */
const URL_SHAPE = /^[a-z][a-z0-9+.-]*:\/\//i;

/**
 * Values that have a digit and a separator but are dates or times, not secrets.
 *
 * `Renewal:` / `2026-10-11` otherwise reads as "short, has a digit, has a
 * symbol" — the password shape. A date is one of the commonest things to write
 * under a heading, so it has to be excluded explicitly.
 */
const DATE_OR_TIME = /^(?:\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{1,2}:\d{2}(?::\d{2})?)$/;

/**
 * Classify one value that sits under a bare label.
 *
 * The signals are weaker here than for an inline `password: x`, because the
 * label is on a different line — so this errs towards MEDIUM and lets the user
 * decide. Returns null when the value looks like ordinary text, which is the
 * common case (`manager`, `ERP_DEMO` are identifiers, not credentials).
 */
function classifyStackedValue(value: string): { type: string; severity: Severity; confidence: number } | null {
  if (!value || isPlaceholder(value)) return null;

  // A URL is an address, not a secret. One that carries `user:pass@` is a
  // credential, and the connection-string rule already catches that shape.
  if (URL_SHAPE.test(value)) return null;

  // A date or a clock time is data, not a credential.
  if (DATE_OR_TIME.test(value)) return null;

  // Anything with whitespace is prose or a `label: value` line, not a value.
  if (/\s/.test(value)) return null;

  const length = value.length;
  const hasDigit = /\d/.test(value);
  const hasSpecial = /[^A-Za-z0-9]/.test(value);
  const hasLower = /[a-z]/.test(value);
  const hasUpper = /[A-Z]/.test(value);
  const entropy = shannonEntropy(value);

  // Long, high-entropy, mixed alphanumeric: the shape of a generated token.
  // This is what catches `dueit73947wuweddnxcc8f938493GhsaggA`.
  if (length >= 20 && hasDigit && entropy >= 3.5 && (hasLower || hasUpper)) {
    return { type: "api_key", severity: "HIGH", confidence: 0.8 };
  }

  // A password shape: short-ish, has a digit, and either a symbol or mixed
  // case. `HGC@2020` qualifies; `ERP_DEMO` and `manager` do not.
  if (length >= 6 && length <= 40 && hasDigit && (hasSpecial || (hasLower && hasUpper))) {
    return {
      type: "password",
      severity: hasSpecial ? "HIGH" : "MEDIUM",
      confidence: hasSpecial ? 0.78 : 0.7,
    };
  }

  return null;
}

/**
 * Find secrets written as a labelled block, one value per line.
 *
 * ```
 * Orange system:
 * manager
 * HGC@2020
 * ```
 *
 * Everything from the line after the label to the next blank line or the next
 * bare label is a candidate value. The label names the findings, because the
 * user's own heading ("Orange system") is a better name than anything derived
 * from the value.
 */
function detectStackedValues(text: string): Finding[] {
  const lines = text.split("\n");
  const lineStarts: number[] = [];
  let offset = 0;
  for (const line of lines) {
    lineStarts.push(offset);
    offset += line.length + 1;
  }

  const findings: Finding[] = [];

  for (let i = 0; i < lines.length; i += 1) {
    const header = BARE_LABEL.exec(lines[i]);
    if (!header) continue;
    const label = header[1].trim();
    if (!label) continue;

    for (let j = i + 1; j < lines.length; j += 1) {
      const raw = lines[j];
      const value = raw.trim();
      if (!value) break; // a blank line ends the block
      if (BARE_LABEL.test(raw)) break; // the next section starts

      const classified = classifyStackedValue(value);
      if (!classified) continue;

      // Offset of the value within its own line, so the span points at the
      // value and not at the leading whitespace.
      const start = lineStarts[j] + raw.indexOf(value);
      const end = start + value.length;

      findings.push({
        id: findingId(start, end, classified.type),
        start,
        end,
        value,
        label,
        type: classified.type,
        severity: classified.severity,
        confidence: classified.confidence,
        entropy: Number(shannonEntropy(value).toFixed(2)),
        selected: classified.severity !== "MEDIUM",
        rule: "stacked_block",
      });
    }
  }

  return findings;
}

/**
 * Magic tags: `[[secret]]…[[/secret]]`.
 *
 * The detector will never catch everything, and the user knows their own data
 * better than any ruleset. Rather than adding a form field and wiring it into
 * the save path, they wrap a value in place and press Scan — the marker is
 * plain text in the note, so nothing new has to be stored, and the existing
 * detect → approve → protect flow does the rest.
 *
 * Nested markers are not supported; the first closing tag ends the span.
 */
const MAGIC_TAG_OPEN = "[[secret]]";
const MAGIC_TAG_CLOSE = "[[/secret]]";

/**
 * Pull out everything the user wrapped in magic tags.
 *
 * The returned spans point at the *value only*, not the markers — so the
 * placeholders that replace them leave the note clean.
 */
function detectManualTags(text: string): Finding[] {
  const findings: Finding[] = [];
  let cursor = 0;

  while (cursor < text.length) {
    const open = text.indexOf(MAGIC_TAG_OPEN, cursor);
    if (open === -1) break;
    const close = text.indexOf(MAGIC_TAG_CLOSE, open + MAGIC_TAG_OPEN.length);
    if (close === -1) break;

    const start = open + MAGIC_TAG_OPEN.length;
    const value = text.slice(start, close);
    cursor = close + MAGIC_TAG_CLOSE.length;

    if (!value.trim()) continue;

    // The label comes from the line the marker sits on, with the marker itself
    // removed — otherwise `login: [[secret]]x[[/secret]]` is named
    // "login: [[secret]]" instead of "login".
    const rawLabel = deriveLabel(text, start, "marked by hand");
    const label =
      rawLabel.replace(MAGIC_TAG_OPEN, "").replace(MAGIC_TAG_CLOSE, "").replace(/[:=\s]+$/, "").trim() ||
      "marked by hand";

    findings.push({
      id: findingId(start, close, "manual"),
      start,
      end: close,
      value,
      // The heading above the marker names it, same as any other finding.
      label,
      type: "manual",
      // The user asserted this is a secret, so it outranks any guess.
      severity: "HIGH",
      confidence: 1,
      entropy: Number(shannonEntropy(value).toFixed(2)),
      selected: true,
      manual: true,
      rule: "magic_tag",
    });
  }

  return findings;
}

/**
 * Remove the magic markers, keeping the values.
 *
 * Called after the placeholders are applied, so `[[secret]]{{secret:k}}[[/secret]]`
 * becomes just `{{secret:k}}` — the marker has done its job once the value is in
 * the vault, and leaving it in the note would be noise.
 *
 * No offset remapping is needed: detection runs on the original text and
 * `resolveOverlaps` keeps the manual finding (confidence 1) over anything it
 * overlaps.
 */
export function stripMagicTags(text: string): string {
  let result = text;
  let removed = 0;

  while (removed < 500) {
    const open = result.indexOf(MAGIC_TAG_OPEN);
    if (open === -1) break;
    const close = result.indexOf(MAGIC_TAG_CLOSE, open + MAGIC_TAG_OPEN.length);
    if (close === -1) break;
    result =
      result.slice(0, open) + result.slice(open + MAGIC_TAG_OPEN.length, close) +
      result.slice(close + MAGIC_TAG_CLOSE.length);
    removed += 1;
  }

  // An unclosed marker is a typo, not content — drop it so it cannot sit in the
  // note forever looking meaningful.
  return result.split(MAGIC_TAG_OPEN).join("").split(MAGIC_TAG_CLOSE).join("");
}

/**
 * Values that look like secrets but are documentation.
 *
 * This is the single most valuable false-positive control for an agent-heavy
 * workspace, because agents emit `API_KEY=<your-api-key>` constantly.
 */
const PLACEHOLDER_PATTERNS: RegExp[] = [
  /^<[^>]+>$/,
  /^\$\{[^}]+\}$/,
  /^\{\{[^}]+\}\}$/,
  /^%[A-Z_]+%$/,
  /^YOUR[_-]/i,
  /^YOUR[A-Z0-9_-]*$/i,
  /^REPLACE[_-]/i,
  /^CHANGE[_-]?ME$/i,
  /^CHANGE[_-]/i,
  /^EXAMPLE[_-]/i,
  /^SAMPLE[_-]/i,
  /^TODO$/i,
  /^REDACTED[_-]?/i,
  /^x{4,}$/i,
  /^\*{4,}$/,
  /^\.{4,}$/,
  /^dummy$/i,
  /^example$/i,
  /^placeholder$/i,
  /^none$/i,
  /^null$/i,
  /^undefined$/i,
  // A bare environment reference is a pointer, not a secret.
  /^process\.env\./,
  /^\$[A-Z_]+$/,
];

/** Our own placeholder format — must never be re-detected as a secret. */
const SMART_TEXT_PLACEHOLDER = /\{\{secret:[^}]+\}\}/;

export function isPlaceholder(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed) return true;
  if (SMART_TEXT_PLACEHOLDER.test(trimmed)) return true;
  return PLACEHOLDER_PATTERNS.some((pattern) => pattern.test(trimmed));
}

/**
 * Shannon entropy in bits per character.
 *
 * Used only to *adjust* confidence, never to decide on its own. A threshold
 * alone (`entropy > 3.5 ⇒ secret`) produces unusable noise: every hash, ID and
 * base64 blob trips it.
 */
export function shannonEntropy(value: string): number {
  if (!value) return 0;
  const counts = new Map<string, number>();
  for (const char of value) {
    counts.set(char, (counts.get(char) ?? 0) + 1);
  }
  let entropy = 0;
  for (const count of counts.values()) {
    const p = count / value.length;
    entropy -= p * Math.log2(p);
  }
  return entropy;
}

/**
 * Derive a human label from the text preceding a match.
 *
 * The user's own words are a better name than anything we could invent —
 * `old password (2024-09-01)` says more than "password #2". Falls back to the
 * rule's type when there is no usable prefix.
 */
function deriveLabel(source: string, start: number, fallback: string): string {
  const lineStart = source.lastIndexOf("\n", start - 1) + 1;
  const prefix = source.slice(lineStart, start);
  // Drop the separator the label was written with, keep the words.
  const cleaned = prefix.replace(/[:=\s]+$/, "").trim();
  if (!cleaned) return fallback;
  // A very long prefix is probably prose, not a label.
  return cleaned.length <= 60 ? cleaned : fallback;
}

/** Build a stable id for a span so checkbox state survives a re-detect. */
function findingId(start: number, end: number, type: string): string {
  return `${start}:${end}:${type}`;
}

/**
 * Scan `text` and return the findings a user should be asked about.
 *
 * Pure and synchronous: same input, same output, no side effects. The caller
 * decides what to do with the result.
 */
export function detectSecrets(text: string): Finding[] {
  if (!text.trim()) return [];

  const candidates: Finding[] = [];

  for (const rule of ALL_RULES) {
    // A `g` regex carries `lastIndex` between calls; reset so a second scan of
    // the same text is not skipped partway through.
    rule.regex.lastIndex = 0;

    let match: RegExpExecArray | null;
    while ((match = rule.regex.exec(text)) !== null) {
      const raw = match[rule.valueGroup];
      if (!raw) continue;

      // Locate the value inside the whole match so offsets point at the secret,
      // not at the label. `indexOf` is safe here because the value is a literal
      // substring of the match.
      const offsetInMatch =
        rule.valueGroup === 0 ? 0 : match[0].lastIndexOf(raw);
      const start = match.index + (offsetInMatch >= 0 ? offsetInMatch : 0);
      const end = start + raw.length;

      if (isPlaceholder(raw)) continue;

      const entropy = shannonEntropy(raw);
      let confidence = rule.confidence;
      if (entropy >= 3.5) confidence += 0.03;
      // A very short value under a contextual label is still a secret the user
      // labelled as one — keep it, just with less confidence.
      if (raw.length < 6) confidence -= 0.1;

      candidates.push({
        id: findingId(start, end, rule.type),
        start,
        end,
        value: raw,
        label: deriveLabel(text, start, rule.type.replace(/_/g, " ")),
        type: rule.type,
        severity: rule.severity,
        confidence: Math.max(0, Math.min(confidence, 0.999)),
        entropy: Number(entropy.toFixed(2)),
        // MEDIUM findings are plausible but not certain — let the user opt in
        // rather than pre-selecting something we are not sure about.
        selected: rule.severity !== "MEDIUM",
        rule: rule.id,
      });
    }
  }

  return resolveOverlaps([...candidates, ...detectStackedValues(text), ...detectManualTags(text)]);
}

/**
 * Drop overlapping findings, keeping the strongest.
 *
 * `google password: 1234567` matches the password rule *and* the generic key
 * rule (the word "password" contains no "key", but `robot key: xxxx` matches
 * several). Reporting both would show the user two checkboxes for one value,
 * and protecting both would write the same secret twice.
 */
function resolveOverlaps(findings: Finding[]): Finding[] {
  const sorted = [...findings].sort(
    (a, b) =>
      b.confidence - a.confidence ||
      SEVERITY_RANK[b.severity] - SEVERITY_RANK[a.severity] ||
      b.end - b.start - (a.end - a.start),
  );

  const accepted: Finding[] = [];
  for (const candidate of sorted) {
    const overlaps = accepted.some(
      (other) => candidate.start < other.end && other.start < candidate.end,
    );
    if (!overlaps) accepted.push(candidate);
  }

  return accepted.sort((a, b) => a.start - b.start);
}

/**
 * A short human explanation of why a finding was flagged.
 *
 * The review list shows this so the user can judge a MEDIUM finding instead of
 * trusting a bare percentage.
 */
export function ruleReason(finding: Finding): string {
  switch (finding.rule) {
    case "magic_tag":
      return "you marked it by hand";
    case "stacked_block":
      return "a value on its own line under a heading";
    case "private_key":
      return "a private-key header";
    case "github_pat":
    case "github_pat_fine":
      return "a GitHub token format";
    case "slack_token":
      return "a Slack token format";
    case "google_api_key":
      return "a Google API key format";
    case "openai_key":
      return "an OpenAI key format";
    case "jwt":
      return "a JWT format";
    case "connection_string":
      return "a connection string with a password";
    case "bearer":
      return "a Bearer token in a header";
    case "password_assignment":
      return "the word password next to a value";
    case "key_assignment":
      return "a key/token label next to a value";
    default:
      return "a secret-like pattern";
  }
}

/** The `sn-…` key a finding is stored under in Infisical. */
export function secretKeyFor(label: string, type: string): string {
  const slug = label
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40);
  // 6 hex chars keep two same-labelled secrets ("old password" twice) distinct
  // without a lookup, and are short enough to read in the placeholder.
  const suffix = Math.random().toString(16).slice(2, 8);
  return `sn-${slug || type}-${suffix}`;
}

/** Render a key back into the placeholder the note text carries. */
export function placeholderFor(key: string): string {
  return `{{secret:${key}}}`;
}

export const PLACEHOLDER_PATTERN = /\{\{secret:([^}]+)\}\}/g;

/** Everything in `text` that is a placeholder, in order. */
export function extractPlaceholderKeys(text: string): string[] {
  const keys: string[] = [];
  const pattern = new RegExp(PLACEHOLDER_PATTERN.source, "g");
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) {
    keys.push(match[1]);
  }
  return keys;
}

/**
 * Replace the selected findings' values with placeholders.
 *
 * Works back-to-front so each replacement does not shift the offsets of the
 * ones still to come — the classic in-place splice bug.
 */
export function applyPlaceholders(
  text: string,
  replacements: { start: number; end: number; placeholder: string }[],
): string {
  let result = text;
  for (const item of [...replacements].sort((a, b) => b.start - a.start)) {
    result = result.slice(0, item.start) + item.placeholder + result.slice(item.end);
  }
  return result;
}

/** Split `text` into plain runs and placeholder runs for rendering. */
export type Segment =
  | { kind: "text"; value: string }
  | { kind: "secret"; key: string; raw: string };

export function segmentText(text: string): Segment[] {
  const segments: Segment[] = [];
  const pattern = new RegExp(PLACEHOLDER_PATTERN.source, "g");
  let cursor = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > cursor) {
      segments.push({ kind: "text", value: text.slice(cursor, match.index) });
    }
    segments.push({ kind: "secret", key: match[1], raw: match[0] });
    cursor = match.index + match[0].length;
  }

  if (cursor < text.length) {
    segments.push({ kind: "text", value: text.slice(cursor) });
  }

  return segments;
}
