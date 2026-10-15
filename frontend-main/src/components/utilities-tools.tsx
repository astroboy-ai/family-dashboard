"use client";

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, Braces, Code2, FileText, Hash, Network, Plus, QrCode, ScanLine, Search, Trash2, X } from "lucide-react";
import qrcode from "qrcode-generator";
import jsQR from "jsqr";

// qrcode-generator ships a Latin-1 byte encoder, which mangles any non-ASCII
// text (CJK, emoji, accented names) into bytes no scanner can read back — and
// its ESM build (the one webpack picks) omits the UTF-8 helper entirely. So we
// install our own UTF-8 encoder and every generated code round-trips.
qrcode.stringToBytes = (s: string) => Array.from(new TextEncoder().encode(s));

export type Utility = {
  id: string;
  label: string;
  description: string;
  icon: React.ComponentType<{ size?: number | string; className?: string }>;
  group: string;
  /**
   * For tools that genuinely need a keyboard, a big canvas, or a file picker
   * worth more screen than a phone has. Everything is responsive by default —
   * set this only when the tool cannot work at all on a narrow screen, because
   * it hides the tool rather than degrading it.
   */
  desktopOnly?: boolean;
};

export const utilities: Utility[] = [
  { id: "json", label: "JSON Viewer", description: "Validate, beautify, minify, tree view", icon: Braces, group: "Developer" },
  { id: "markdown", label: "Markdown Viewer", description: "Render Markdown with formatting", icon: FileText, group: "Developer" },
  { id: "code", label: "Code Highlighter", description: "Syntax highlight for code files", icon: Code2, group: "Developer" },
  { id: "hash", label: "Hash Tool", description: "MD5, SHA1, SHA256, etc.", icon: Hash, group: "Developer" },
  { id: "archify", label: "Archify Viewer", description: "Store and view Archify interactive HTML diagrams.", icon: Network, group: "Developer" },
  { id: "qr-scanner", label: "QR Scanner", description: "Scan QR codes with camera", icon: ScanLine, group: "Tools" },
  { id: "qr-generator", label: "QR Generator", description: "Generate scannable QR codes", icon: QrCode, group: "Tools" },
];

/** True while the viewport is phone-width. Drives the desktop-only gating. */
export function useIsNarrow() {
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(max-width: 760px)");
    const update = () => setNarrow(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return narrow;
}

function JsonValidator({ onClose }: { onClose: () => void }) {
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [error, setError] = useState("");
  const [view, setView] = useState<"tree" | "pretty" | "minified">("tree");
  const [parsed, setParsed] = useState<unknown>(null);

  function validate() {
    try {
      const result = JSON.parse(input);
      setParsed(result);
      setOutput(JSON.stringify(result, null, 2));
      setError("");
    } catch (e) {
      setParsed(null);
      setOutput("");
      setError(e instanceof Error ? e.message : "Invalid JSON");
    }
  }

  function minify() {
    if (parsed === null) return;
    setOutput(JSON.stringify(parsed));
  }

  function beautify() {
    if (parsed === null) return;
    setOutput(JSON.stringify(parsed, null, 2));
  }

  return (
    <div className="utility-panel">
      <div className="utility-panel-header">
        <h2>JSON Viewer</h2>
        <button className="icon-button" onClick={onClose} aria-label="Close">✕</button>
      </div>
      <textarea
        className="utility-textarea"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder="Paste JSON here…"
        rows={8}
      />
      <div className="utility-action-row">
        <button className="primary-button" onClick={validate}>Validate</button>
        <button className="secondary-button" onClick={beautify} disabled={parsed === null}>Beautify</button>
        <button className="secondary-button" onClick={minify} disabled={parsed === null}>Minify</button>
        <button className="secondary-button" onClick={() => { setInput(""); setOutput(""); setError(""); setParsed(null); }}>Clear</button>
      </div>
      {error && <p className="utility-error">{error}</p>}
      {parsed !== null && (
        <div className="json-viewer">
          <div className="json-viewer-toolbar">
            <button className={`json-viewer-tab${view === "tree" ? " active" : ""}`} onClick={() => setView("tree")}>Tree</button>
            <button className={`json-viewer-tab${view === "pretty" ? " active" : ""}`} onClick={() => setView("pretty")}>Pretty</button>
            <button className={`json-viewer-tab${view === "minified" ? " active" : ""}`} onClick={() => setView("minified")}>Minified</button>
          </div>
          {view === "tree" && <JsonTree data={parsed} />}
          {view === "pretty" && <pre className="utility-output">{JSON.stringify(parsed, null, 2)}</pre>}
          {view === "minified" && <pre className="utility-output">{JSON.stringify(parsed)}</pre>}
        </div>
      )}
    </div>
  );
}

function JsonTree({ data, name, depth = 0 }: { data: unknown; name?: string; depth?: number }) {
  const [collapsed, setCollapsed] = useState(false);
  const isObject = data !== null && typeof data === "object";
  const isArray = Array.isArray(data);
  const entries = isObject ? (isArray ? data.map((v, i) => [String(i), v] as const) : Object.entries(data as Record<string, unknown>)) : [];
  const preview = isArray ? `[${data.length} items]` : `{${entries.length} keys}`;

  if (!isObject) {
    return (
      <div className="json-tree-leaf" style={{ paddingLeft: depth * 16 }}>
        {name !== undefined && <span className="json-tree-key">{name}: </span>}
        <span className={`json-tree-value json-tree-${typeof data}`}>{JSON.stringify(data)}</span>
      </div>
    );
  }

  return (
    <div className="json-tree-node" style={{ paddingLeft: depth * 16 }}>
      <button className="json-tree-toggle" onClick={() => setCollapsed(!collapsed)}>
        <span className="json-tree-arrow">{collapsed ? "▶" : "▼"}</span>
        {name !== undefined && <span className="json-tree-key">{name}: </span>}
        <span className="json-tree-preview">{preview}</span>
      </button>
      {!collapsed && (
        <div className="json-tree-children">
          {entries.map(([key, value]) => (
            <JsonTree key={key} data={value} name={key} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * MD5 in plain JS.
 *
 * WebCrypto has no MD5 — `crypto.subtle.digest("MD5", …)` rejects, which is why
 * the SHA algorithms come from the browser and MD5 has to be implemented here.
 */
function md5(input: string): string {
  function toWords(str: string): number[] {
    const bytes: number[] = [];
    for (let i = 0; i < str.length; i++) {
      const code = str.charCodeAt(i);
      if (code < 0x80) bytes.push(code);
      else if (code < 0x800) bytes.push(0xc0 | (code >> 6), 0x80 | (code & 0x3f));
      else if (code < 0xd800 || code >= 0xe000) {
        bytes.push(0xe0 | (code >> 12), 0x80 | ((code >> 6) & 0x3f), 0x80 | (code & 0x3f));
      } else {
        i++;
        const cp = 0x10000 + (((code & 0x3ff) << 10) | (str.charCodeAt(i) & 0x3ff));
        bytes.push(
          0xf0 | (cp >> 18),
          0x80 | ((cp >> 12) & 0x3f),
          0x80 | ((cp >> 6) & 0x3f),
          0x80 | (cp & 0x3f),
        );
      }
    }
    const bitLen = bytes.length * 8;
    bytes.push(0x80);
    while (bytes.length % 64 !== 56) bytes.push(0);
    const words: number[] = [];
    for (let i = 0; i < bytes.length; i += 4) {
      words.push(bytes[i] | (bytes[i + 1] << 8) | (bytes[i + 2] << 16) | (bytes[i + 3] << 24));
    }
    words.push(bitLen >>> 0, Math.floor(bitLen / 0x100000000) >>> 0);
    return words;
  }

  const add = (a: number, b: number) => (a + b) >>> 0;
  const rol = (value: number, shift: number) => ((value << shift) | (value >>> (32 - shift))) >>> 0;

  const S = [
    7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22,
    5, 9, 14, 20, 5, 9, 14, 20, 5, 9, 14, 20, 5, 9, 14, 20,
    4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23,
    6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21,
  ];
  const K: number[] = [];
  for (let i = 0; i < 64; i++) K.push(Math.floor(Math.abs(Math.sin(i + 1)) * 0x100000000) >>> 0);

  const words = toWords(input);
  let a0 = 0x67452301;
  let b0 = 0xefcdab89;
  let c0 = 0x98badcfe;
  let d0 = 0x10325476;

  for (let chunk = 0; chunk < words.length; chunk += 16) {
    const M = words.slice(chunk, chunk + 16);
    let [A, B, C, D] = [a0, b0, c0, d0];
    for (let i = 0; i < 64; i++) {
      let F: number;
      let g: number;
      if (i < 16) {
        F = (B & C) | (~B & D);
        g = i;
      } else if (i < 32) {
        F = (D & B) | (~D & C);
        g = (5 * i + 1) % 16;
      } else if (i < 48) {
        F = B ^ C ^ D;
        g = (3 * i + 5) % 16;
      } else {
        F = C ^ (B | ~D);
        g = (7 * i) % 16;
      }
      F = add(add(add(F, A), K[i]), M[g]);
      A = D;
      D = C;
      C = B;
      B = add(B, rol(F, S[i]));
    }
    a0 = add(a0, A);
    b0 = add(b0, B);
    c0 = add(c0, C);
    d0 = add(d0, D);
  }

  const hex = (n: number) => {
    let out = "";
    for (let i = 0; i < 4; i++) out += ((n >>> (i * 8)) & 0xff).toString(16).padStart(2, "0");
    return out;
  };
  return hex(a0) + hex(b0) + hex(c0) + hex(d0);
}

const SHA_ALGORITHMS = ["SHA-1", "SHA-256", "SHA-384", "SHA-512"] as const;

function HashTool({ onClose }: { onClose: () => void }) {
  const [input, setInput] = useState("");
  const [hashes, setHashes] = useState<{ algorithm: string; hash: string }[]>([]);
  const [sourceName, setSourceName] = useState("");
  const [busy, setBusy] = useState(false);

  async function computeFromText(text: string, name: string) {
    setBusy(true);
    const results: { algorithm: string; hash: string }[] = [
      { algorithm: "MD5", hash: md5(text) },
    ];
    const encoder = new TextEncoder();
    for (const algo of SHA_ALGORITHMS) {
      try {
        const buffer = await crypto.subtle.digest(algo, encoder.encode(text));
        const hex = Array.from(new Uint8Array(buffer))
          .map((b) => b.toString(16).padStart(2, "0"))
          .join("");
        results.push({ algorithm: algo, hash: hex });
      } catch {
        results.push({ algorithm: algo, hash: "unsupported" });
      }
    }
    setHashes(results);
    setSourceName(name);
    setBusy(false);
  }

  async function handleFile(file: File) {
    setBusy(true);
    const bytes = new Uint8Array(await file.arrayBuffer());
    let binary = "";
    for (let i = 0; i < bytes.length; i += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    }
    const results: { algorithm: string; hash: string }[] = [{ algorithm: "MD5", hash: md5(binary) }];
    for (const algo of SHA_ALGORITHMS) {
      try {
        const buffer = await crypto.subtle.digest(algo, bytes);
        const hex = Array.from(new Uint8Array(buffer))
          .map((b) => b.toString(16).padStart(2, "0"))
          .join("");
        results.push({ algorithm: algo, hash: hex });
      } catch {
        results.push({ algorithm: algo, hash: "unsupported" });
      }
    }
    setHashes(results);
    setSourceName(`${file.name} (${bytes.length.toLocaleString()} bytes)`);
    setBusy(false);
  }

  return (
    <div className="utility-panel">
      <div className="utility-panel-header">
        <h2>Hash Tool</h2>
        <button className="icon-button" onClick={onClose} aria-label="Close">✕</button>
      </div>
      <textarea
        className="utility-textarea"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder="Enter text to hash…"
        rows={4}
      />
      <div className="utility-action-row">
        <button className="primary-button" onClick={() => void computeFromText(input, "text input")} disabled={busy}>
          Compute Hashes
        </button>
        <label className="secondary-button file-picker-button">
          Hash a file…
          <input
            type="file"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void handleFile(file);
            }}
          />
        </label>
      </div>
      {sourceName && <p className="utility-source">Source: {sourceName}</p>}
      {hashes.length > 0 && (
        <div className="hash-results">
          {hashes.map((h) => (
            <div key={h.algorithm} className="hash-row">
              <span className="hash-algo">{h.algorithm}</span>
              <code className="hash-value">{h.hash}</code>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function MarkdownViewer({ onClose }: { onClose: () => void }) {
  const [input, setInput] = useState("");

  return (
    <div className="utility-panel">
      <div className="utility-panel-header">
        <h2>Markdown Viewer</h2>
        <button className="icon-button" onClick={onClose} aria-label="Close">✕</button>
      </div>
      <textarea
        className="utility-textarea"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder="Paste Markdown here…"
        rows={10}
      />
      <div className="utility-action-row">
        <button className="secondary-button" onClick={() => setInput("")}>Clear</button>
      </div>
      {input.trim() && (
        <div className="markdown-viewer">
          <MarkdownRenderer source={input} />
        </div>
      )}
    </div>
  );
}

function MarkdownRenderer({ source }: { source: string }) {
  const lines = source.split("\n");
  const elements: React.ReactNode[] = [];
  let list: string[] = [];
  let inCode = false;
  let codeLines: string[] = [];

  const flushList = () => {
    if (list.length > 0) {
      elements.push(
        <ul key={`list-${elements.length}`}>
          {list.map((item, i) => (
            <li key={i}>{renderInline(item)}</li>
          ))}
        </ul>,
      );
      list = [];
    }
  };

  const renderInline = (text: string): React.ReactNode => {
    const parts: React.ReactNode[] = [];
    let remaining = text;
    let key = 0;

    while (remaining.length > 0) {
      // Bold + italic
      const boldItalic = remaining.match(/^\*\*\*(.+?)\*\*\*/);
      if (boldItalic) {
        parts.push(<strong key={key++}><em>{boldItalic[1]}</em></strong>);
        remaining = remaining.slice(boldItalic[0].length);
        continue;
      }

      // Bold
      const bold = remaining.match(/^\*\*(.+?)\*\*/);
      if (bold) {
        parts.push(<strong key={key++}>{bold[1]}</strong>);
        remaining = remaining.slice(bold[0].length);
        continue;
      }

      // Italic
      const italic = remaining.match(/^\*(.+?)\*/);
      if (italic) {
        parts.push(<em key={key++}>{italic[1]}</em>);
        remaining = remaining.slice(italic[0].length);
        continue;
      }

      // Inline code
      const inlineCode = remaining.match(/^`([^`]+)`/);
      if (inlineCode) {
        parts.push(<code key={key++} className="inline-code">{inlineCode[1]}</code>);
        remaining = remaining.slice(inlineCode[0].length);
        continue;
      }

      // Plain text until next marker
      const next = remaining.search(/[*`]/);
      if (next === -1) {
        parts.push(remaining);
        break;
      }
      parts.push(remaining.slice(0, next));
      remaining = remaining.slice(next);
    }

    return parts;
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Code block
    if (line.startsWith("```")) {
      if (inCode) {
        elements.push(
          <pre key={`code-${i}`} className="code-block"><code>{codeLines.join("\n")}</code></pre>,
        );
        codeLines = [];
        inCode = false;
      } else {
        flushList();
        inCode = true;
      }
      continue;
    }

    if (inCode) {
      codeLines.push(line);
      continue;
    }

    // Headers
    const header = line.match(/^(#{1,6})\s+(.+)$/);
    if (header) {
      flushList();
      const level = header[1].length;
      const content = renderInline(header[2]);
      const headerTags = ["h1", "h2", "h3", "h4", "h5", "h6"] as const;
      const Tag = headerTags[Math.min(level, 6) - 1];
      elements.push(<Tag key={i}>{content}</Tag>);
      continue;
    }

    // List items
    const listItem = line.match(/^\s*[-*]\s+(.+)$/);
    if (listItem) {
      list.push(listItem[1]);
      continue;
    }

    // Ordered list items
    const orderedItem = line.match(/^\s*\d+\.\s+(.+)$/);
    if (orderedItem) {
      list.push(orderedItem[1]);
      continue;
    }

    // Blank line
    if (!line.trim()) {
      flushList();
      continue;
    }

    // Paragraph
    flushList();
    elements.push(<p key={i}>{renderInline(line)}</p>);
  }

  flushList();

  return <>{elements}</>;
}

function CodeHighlighter({ onClose }: { onClose: () => void }) {
  const [input, setInput] = useState("");
  const [language, setLanguage] = useState("javascript");

  const languages = [
    { id: "javascript", label: "JavaScript" },
    { id: "html", label: "HTML" },
    { id: "css", label: "CSS" },
    { id: "json", label: "JSON" },
    { id: "ini", label: "INI / Config" },
    { id: "bash", label: "Bash / Shell" },
    { id: "python", label: "Python" },
    { id: "sql", label: "SQL" },
  ];

  return (
    <div className="utility-panel">
      <div className="utility-panel-header">
        <h2>Code Highlighter</h2>
        <button className="icon-button" onClick={onClose} aria-label="Close">✕</button>
      </div>
      <label className="field">
        <span>Language</span>
        <select value={language} onChange={(e) => setLanguage(e.target.value)}>
          {languages.map((lang) => (
            <option key={lang.id} value={lang.id}>{lang.label}</option>
          ))}
        </select>
      </label>
      <textarea
        className="utility-textarea"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder="Paste code here…"
        rows={12}
        spellCheck={false}
      />
      <div className="utility-action-row">
        <button className="secondary-button" onClick={() => setInput("")}>Clear</button>
      </div>
      {input.trim() && (
        <pre className="code-highlighter">
          <code dangerouslySetInnerHTML={{ __html: highlightCode(input, language) }} />
        </pre>
      )}
    </div>
  );
}

function highlightCode(code: string, language: string): string {
  let result = code
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  const patterns: Record<string, { pattern: RegExp; className: string }[]> = {
    javascript: [
      { pattern: /\/\/.*$/gm, className: "tok-comment" },
      { pattern: /\/\*[\s\S]*?\*\//g, className: "tok-comment" },
      { pattern: /`[^`]*`/g, className: "tok-string" },
      { pattern: /'[^']*'/g, className: "tok-string" },
      { pattern: /"[^"]*"/g, className: "tok-string" },
      { pattern: /\b(function|const|let|var|if|else|for|while|return|class|new|import|export|from|async|await|try|catch|throw|typeof|instanceof)\b/g, className: "tok-keyword" },
      { pattern: /\b(true|false|null|undefined|NaN|Infinity)\b/g, className: "tok-literal" },
      { pattern: /\b(\d+\.?\d*)\b/g, className: "tok-number" },
    ],
    html: [
      { pattern: /&lt;!--[\s\S]*?--&gt;/g, className: "tok-comment" },
      { pattern: /&lt;\/?[a-zA-Z][^&]*?&gt;/g, className: "tok-tag" },
      { pattern: /[a-zA-Z-]+="[^"]*"/g, className: "tok-attr" },
    ],
    css: [
      { pattern: /\/\*[\s\S]*?\*\//g, className: "tok-comment" },
      { pattern: /[a-zA-Z-]+:/g, className: "tok-property" },
      { pattern: /[.#][a-zA-Z][\w-]*/g, className: "tok-selector" },
      { pattern: /"[^"]*"/g, className: "tok-string" },
      { pattern: /'[^']*'/g, className: "tok-string" },
      { pattern: /\b(px|em|rem|vh|vw|%)\b/g, className: "tok-unit" },
    ],
    json: [
      { pattern: /"[^"]*":/g, className: "tok-key" },
      { pattern: /"[^"]*"/g, className: "tok-string" },
      { pattern: /\b(true|false|null)\b/g, className: "tok-literal" },
      { pattern: /\b(\d+\.?\d*)\b/g, className: "tok-number" },
    ],
    ini: [
      { pattern: /;.*$/gm, className: "tok-comment" },
      { pattern: /^\s*\[.*\]\s*$/gm, className: "tok-section" },
      { pattern: /^[a-zA-Z_][\w]*(?=\s*=)/gm, className: "tok-key" },
      { pattern: /"[^"]*"/g, className: "tok-string" },
      { pattern: /'[^']*'/g, className: "tok-string" },
    ],
    bash: [
      { pattern: /#.*$/gm, className: "tok-comment" },
      { pattern: /"[^"]*"/g, className: "tok-string" },
      { pattern: /'[^']*'/g, className: "tok-string" },
      { pattern: /\b(echo|if|then|else|fi|for|do|done|while|function|exit|return|cd|ls|mkdir|rm|cp|mv|chmod|chown|sudo|apt|pip|npm|node|python|git)\b/g, className: "tok-keyword" },
      { pattern: /\$(\w+|\{[^}]*\})/g, className: "tok-variable" },
    ],
    python: [
      { pattern: /#.*$/gm, className: "tok-comment" },
      { pattern: /"""[\s\S]*?"""|'''[\s\S]*?'''/g, className: "tok-string" },
      { pattern: /"[^"]*"/g, className: "tok-string" },
      { pattern: /'[^']*'/g, className: "tok-string" },
      { pattern: /\b(def|class|if|elif|else|for|while|return|import|from|as|try|except|finally|with|lambda|pass|break|continue|yield|global|nonlocal|assert|raise)\b/g, className: "tok-keyword" },
      { pattern: /\b(True|False|None)\b/g, className: "tok-literal" },
      { pattern: /\b(\d+\.?\d*)\b/g, className: "tok-number" },
    ],
    sql: [
      { pattern: /--.*$/gm, className: "tok-comment" },
      { pattern: /\/\*[\s\S]*?\*\//g, className: "tok-comment" },
      { pattern: /'[^']*'/g, className: "tok-string" },
      { pattern: /\b(SELECT|INSERT|UPDATE|DELETE|FROM|WHERE|JOIN|LEFT|RIGHT|INNER|OUTER|ON|GROUP|BY|ORDER|HAVING|LIMIT|OFFSET|AS|AND|OR|NOT|NULL|IS|IN|EXISTS|BETWEEN|LIKE|DISTINCT|UNION|ALL|CASE|WHEN|THEN|ELSE|END|CREATE|TABLE|ALTER|DROP|INDEX|VIEW|INTO|VALUES|SET|PRIMARY|KEY|FOREIGN|REFERENCES|CONSTRAINT|DEFAULT|UNIQUE|CHECK|CASCADE|RESTRICT|BEGIN|COMMIT|ROLLBACK|TRANSACTION|GRANT|REVOKE|TO|USER|DATABASE|SCHEMA|SHOW|DESCRIBE|EXPLAIN|ANALYZE|VACUUM|ATTACH|DETACH|PRAGMA|USE|DISTINCT|TOP|BOTTOM|PERCENT|TIES|WITH|RECURSIVE|OVER|PARTITION|WINDOW|RANGE|ROWS|UNBOUNDED|PRECEDING|FOLLOWING|CURRENT|ROW|EXCLUDE|OTHERS|FIRST|LAST|NULLS)\b/gi, className: "tok-keyword" },
      { pattern: /\b(\d+\.?\d*)\b/g, className: "tok-number" },
    ],
  };

  const langPatterns = patterns[language] || patterns.javascript;
  for (const { pattern, className } of langPatterns) {
    result = result.replace(pattern, (match) => `<span class="${className}">${match}</span>`);
  }

  return result;
}

function QRScanner({ onClose }: { onClose: () => void }) {
  const [result, setResult] = useState("");
  const [error, setError] = useState("");
  const [scanning, setScanning] = useState(false);
  const [copied, setCopied] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const rafRef = useRef<number | null>(null);

  /** Stop the camera and the decode loop. Safe to call when idle. */
  const stop = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setScanning(false);
  }, []);

  // Releasing the camera on unmount matters: a still-open stream keeps the
  // browser's camera light on and blocks the next scan.
  useEffect(() => stop, [stop]);

  /** One decode frame. Keeps re-queuing until a code is read or the user stops. */
  const tick = useCallback(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;
    if (video.readyState === video.HAVE_ENOUGH_DATA && video.videoWidth > 0) {
      const width = video.videoWidth;
      const height = video.videoHeight;
      canvas.width = width;
      canvas.height = height;
      const context = canvas.getContext("2d", { willReadFrequently: true });
      if (context) {
        context.drawImage(video, 0, 0, width, height);
        const frame = context.getImageData(0, 0, width, height);
        const code = jsQR(frame.data, width, height, { inversionAttempts: "dontInvert" });
        if (code?.data) {
          setResult(code.data);
          stop();
          return;
        }
      }
    }
    rafRef.current = requestAnimationFrame(tick);
  }, [stop]);

  async function startScan() {
    setError("");
    setResult("");
    setCopied(false);
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("This browser can't open the camera. Use “Decode an image” instead.");
      return;
    }
    setScanning(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
      streamRef.current = stream;
      const video = videoRef.current;
      if (!video) return;
      video.srcObject = stream;
      await video.play();
      rafRef.current = requestAnimationFrame(tick);
    } catch (err) {
      setScanning(false);
      setError(err instanceof Error ? err.message : "Camera access denied");
    }
  }

  /** Decode a saved photo — the reliable path on devices that block camera. */
  async function decodeFile(file: File) {
    setError("");
    setResult("");
    setCopied(false);
    stop();
    try {
      const bitmap = await createImageBitmap(file);
      const canvas = canvasRef.current;
      if (!canvas) return;
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
      const context = canvas.getContext("2d", { willReadFrequently: true });
      if (!context) return;
      context.drawImage(bitmap, 0, 0);
      const frame = context.getImageData(0, 0, bitmap.width, bitmap.height);
      const code = jsQR(frame.data, bitmap.width, bitmap.height, { inversionAttempts: "attemptBoth" });
      if (code?.data) setResult(code.data);
      else setError("No QR code found in that image.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't read that image.");
    }
  }

  async function copyResult() {
    try {
      await navigator.clipboard.writeText(result);
      setCopied(true);
    } catch {
      setError("Couldn't copy — select the text and copy it manually.");
    }
  }

  return (
    <div className="utility-panel">
      <div className="utility-panel-header">
        <h2>QR Scanner</h2>
        <button className="icon-button" onClick={onClose} aria-label="Close">✕</button>
      </div>
      <div className="qr-scanner-body">
        <div className="qr-video-wrap">
          <video ref={videoRef} className="qr-video" playsInline muted />
          {!scanning && !result && (
            <p className="utility-hint">Point your camera at a QR code, or decode a saved image.</p>
          )}
        </div>
        <canvas ref={canvasRef} style={{ display: "none" }} />
        <div className="qr-actions">
          {scanning ? (
            <button className="secondary-button" onClick={stop}>Stop camera</button>
          ) : (
            <button className="primary-button" onClick={() => void startScan()}>Start camera</button>
          )}
          <label className="secondary-button qr-file-button">
            Decode an image
            <input
              type="file"
              accept="image/*"
              hidden
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void decodeFile(file);
                event.target.value = "";
              }}
            />
          </label>
        </div>
        {error && <p className="utility-error">{error}</p>}
        {result && (
          <div className="qr-result">
            <p className="utility-hint">Scanned result:</p>
            <p className="utility-result qr-result-text">{result}</p>
            <div className="qr-actions">
              <button className="secondary-button" onClick={() => void copyResult()}>
                {copied ? "Copied" : "Copy"}
              </button>
              {/^https?:\/\//i.test(result) && (
                <a className="secondary-button" href={result} target="_blank" rel="noopener noreferrer">
                  Open link
                </a>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function QRGenerator({ onClose }: { onClose: () => void }) {
  const [text, setText] = useState("");
  const [size, setSize] = useState(256);
  const [error, setError] = useState("");
  const [generated, setGenerated] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  /**
   * Encode `text` and paint it onto the canvas.
   *
   * typeNumber 0 lets the library pick the smallest version that fits; "M" is
   * the usual error-correction level (recovers ~15% damage). A 2-module quiet
   * zone is drawn because scanners need the white margin to find the code.
   */
  function generate() {
    const value = text.trim();
    if (!value) return;
    setError("");
    try {
      const qr = qrcode(0, "M");
      qr.addData(value);
      qr.make();
      const count = qr.getModuleCount();
      const canvas = canvasRef.current;
      if (!canvas) return;
      const context = canvas.getContext("2d");
      if (!context) return;
      const margin = 2;
      const cell = Math.max(2, Math.floor(size / (count + margin * 2)));
      const dim = (count + margin * 2) * cell;
      canvas.width = dim;
      canvas.height = dim;
      context.fillStyle = "#ffffff";
      context.fillRect(0, 0, dim, dim);
      context.fillStyle = "#000000";
      for (let row = 0; row < count; row += 1) {
        for (let col = 0; col < count; col += 1) {
          if (qr.isDark(row, col)) {
            context.fillRect((col + margin) * cell, (row + margin) * cell, cell, cell);
          }
        }
      }
      setGenerated(true);
    } catch (err) {
      setGenerated(false);
      setError(err instanceof Error ? err.message : "Couldn't encode that. Try shorter content.");
    }
  }

  function download() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const link = document.createElement("a");
    link.download = "qr-code.png";
    link.href = canvas.toDataURL("image/png");
    link.click();
  }

  return (
    <div className="utility-panel">
      <div className="utility-panel-header">
        <h2>QR Generator</h2>
        <button className="icon-button" onClick={onClose} aria-label="Close">✕</button>
      </div>
      <div className="qr-generator-body">
        <label className="field">
          <span>Content</span>
          <textarea
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setGenerated(false);
            }}
            placeholder="Enter text or URL to encode…"
            rows={3}
          />
        </label>
        <label className="field">
          <span>Size (px)</span>
          <input
            type="number"
            min={128}
            max={1024}
            step={16}
            value={size}
            onChange={(e) => {
              setSize(Number(e.target.value) || 256);
              setGenerated(false);
            }}
          />
        </label>
        <button className="primary-button" onClick={generate} disabled={!text.trim()}>
          Generate
        </button>
        {error && <p className="utility-error">{error}</p>}
        {/* Kept mounted so the ref is live when generate() first runs. */}
        <div className="qr-result" style={{ display: generated ? undefined : "none" }}>
          <p className="utility-hint">Scan with any QR reader:</p>
          <canvas ref={canvasRef} className="qr-canvas" />
          <button className="secondary-button" onClick={download}>Download PNG</button>
        </div>
      </div>
    </div>
  );
}


/**
 * Render one tool by id.
 *
 * Each tool keeps its own header and close button, and that button is what
 * closes the drawer — so once a tool is open the drawer has no header of its
 * own and the tool owns the full panel.
 */
export function UtilityBody({ id, onClose }: { id: string; onClose: () => void }) {
  switch (id) {
    case "json": return <JsonValidator onClose={onClose} />;
    case "markdown": return <MarkdownViewer onClose={onClose} />;
    case "code": return <CodeHighlighter onClose={onClose} />;
    case "hash": return <HashTool onClose={onClose} />;
    case "qr-scanner": return <QRScanner onClose={onClose} />;
    case "qr-generator": return <QRGenerator onClose={onClose} />;
    case "archify": return <ArchifyViewer onClose={onClose} />;
    default: return null;
  }
}


// ── Archify Viewer ────────────────────────────────────────────────
//
// Standalone Archify HTML diagrams, stored verbatim and rendered in a
// sandboxed iframe. Agents file these with create_archify_diagram after
// running Archify's finalize step; the viewer never serves them as a route.

type ArchifyDiagramSummary = {
  id: string;
  title: string | null;
  type: string | null;
  created_at: string;
  updated_at: string;
  tags: { slug: string; name: string }[];
};

type ArchifyDiagramDetail = ArchifyDiagramSummary & {
  html: string | null;
  created_by: string | null;
};

export function ArchifyViewer({ onClose }: { onClose: () => void }) {
  const [view, setView] = useState<"list" | "detail" | "create">("list");
  const [diagrams, setDiagrams] = useState<ArchifyDiagramSummary[]>([]);
  const [active, setActive] = useState<ArchifyDiagramDetail | null>(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ title: "", type: "architecture", html: "" });
  const [saving, setSaving] = useState(false);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const q = search.trim();
      const res = await fetch(`/api/archify${q ? `?search=${encodeURIComponent(q)}` : ""}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setDiagrams(data.diagrams ?? []);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load diagrams");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [search]);

  async function openDetail(id: string) {
    setError("");
    try {
      const res = await fetch(`/api/archify/${id}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setActive(data);
      setView("detail");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load diagram");
    }
  }

  async function createDiagram() {
    setSaving(true);
    setError("");
    try {
      const res = await fetch("/api/archify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setForm({ title: "", type: "architecture", html: "" });
      setView("list");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to create diagram");
    } finally {
      setSaving(false);
    }
  }

  async function deleteDiagram(id: string) {
    if (!window.confirm("Delete this diagram? This cannot be undone.")) return;
    setError("");
    try {
      const res = await fetch(`/api/archify/${id}`, { method: "DELETE" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      if (active?.id === id) {
        setActive(null);
        setView("list");
      }
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to delete diagram");
    }
  }

  if (view === "create") {
    return (
      <div className="utility-panel">
        <div className="utility-panel-header">
          <h2>New diagram</h2>
          <button className="icon-button" onClick={() => setView("list")} aria-label="Back to diagrams">
            <ArrowLeft size={16} />
          </button>
        </div>
        <div className="utility-panel-body">
          <label className="utility-field">
            <span>Title</span>
            <input
              value={form.title}
              onChange={(event) => setForm({ ...form, title: event.target.value })}
              placeholder="My architecture"
            />
          </label>
          <label className="utility-field">
            <span>Type</span>
            <select value={form.type} onChange={(event) => setForm({ ...form, type: event.target.value })}>
              <option value="architecture">Architecture</option>
              <option value="workflow">Workflow</option>
              <option value="sequence">Sequence</option>
              <option value="dataflow">Dataflow</option>
              <option value="lifecycle">Lifecycle</option>
              <option value="erd">ERD</option>
              <option value="class">Class</option>
              <option value="tree">Tree</option>
              <option value="timeline">Timeline</option>
              <option value="waterfall">Waterfall</option>
            </select>
          </label>
          <label className="utility-field">
            <span>HTML</span>
            <textarea
              value={form.html}
              onChange={(event) => setForm({ ...form, html: event.target.value })}
              placeholder="Paste the standalone HTML from Archify's finalize step…"
              rows={14}
            />
          </label>
          {error && <p className="inline-error" role="alert">{error}</p>}
          <div className="utility-action-row">
            <button
              className="primary-button"
              onClick={() => void createDiagram()}
              disabled={saving || !form.html.trim()}
            >
              {saving ? "Saving…" : "Save diagram"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (view === "detail" && active) {
    return (
      <div className="utility-panel">
        <div className="utility-panel-header">
          <h2>{active.title ?? "Untitled diagram"}</h2>
          <button
            className="icon-button"
            onClick={() => {
              setActive(null);
              setView("list");
            }}
            aria-label="Back to diagrams"
          >
            <ArrowLeft size={16} />
          </button>
        </div>
        <div className="utility-panel-body">
          <div className="archify-meta">
            <span>{active.type ?? "diagram"}</span>
            <span>Updated {new Date(active.updated_at).toLocaleDateString()}</span>
          </div>
          {active.html && (
            <iframe
              srcDoc={active.html}
              sandbox="allow-scripts"
              className="archify-viewer"
              title={active.title ?? "Archify diagram"}
            />
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="utility-panel">
      <div className="utility-panel-header">
        <h2>Archify diagrams</h2>
        <button className="icon-button" onClick={onClose} aria-label="Close">
          <X size={16} />
        </button>
      </div>
      <div className="utility-panel-body">
        <div className="archify-toolbar">
          <label className="search-field archify-search">
            <Search size={14} />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search diagrams…"
              aria-label="Search diagrams"
            />
          </label>
          <button className="primary-button" onClick={() => setView("create")}>
            <Plus size={14} /> New
          </button>
        </div>
        {loading ? (
          <p className="inline-helper">Loading…</p>
        ) : error ? (
          <p className="inline-error" role="alert">{error}</p>
        ) : diagrams.length === 0 ? (
          <p className="inline-helper">No diagrams yet. Create one by pasting Archify HTML.</p>
        ) : (
          <div className="archify-list">
            {diagrams.map((diagram) => (
              <div key={diagram.id} className="archify-item">
                <button className="archify-item-main" onClick={() => void openDetail(diagram.id)}>
                  <span className="archify-item-title">{diagram.title ?? "Untitled"}</span>
                  <span className="archify-item-meta">
                    {diagram.type ?? "diagram"} · {new Date(diagram.updated_at).toLocaleDateString()}
                  </span>
                  {diagram.tags.length > 0 && (
                    <span className="archify-item-tags">
                      {diagram.tags.map((tag) => (
                        <span key={tag.slug} className="archify-tag">#{tag.slug}</span>
                      ))}
                    </span>
                  )}
                </button>
                <button
                  className="icon-button archify-item-delete"
                  onClick={() => void deleteDiagram(diagram.id)}
                  aria-label={`Delete ${diagram.title ?? "diagram"}`}
                  title="Delete diagram"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
