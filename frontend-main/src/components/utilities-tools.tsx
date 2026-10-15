"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { createBlock, createTextBlock, uploadFile } from "@/lib/api";
import { ArrowLeft, Braces, Camera, Code2, Download, FileText, Hash, Network, Plus, QrCode, ScanLine, Search, Trash2, X } from "lucide-react";
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
  { id: "qr-scanner", label: "QR Scanner", description: "Scan QR codes (camera or image)", icon: ScanLine, group: "Tools" },
  { id: "qr-generator", label: "QR Generator", description: "Generate QR codes & barcodes", icon: QrCode, group: "Tools" },
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

/**
 * ── QR codes & barcodes
 *
 * Reader:     jsQR            (QR / Micro QR — camera + image decode)
 * QR writer:  qrcode-generator  (ISO/IEC 18004, UTF-8 encoder fixed at module load)
 * Barcodes:   bwip-js           (Code 128, EAN-13/8, UPC-A, Code 39, ITF-14) — lazy
 *   imported, so the heavier dependency only lands when a barcode is rendered.
 *
 * Every writer paints onto an HTMLCanvasElement — the shared primitive that
 * lets the scanner re-render a scanned value ("duplicate the code") and lets
 * both tools save the rendered code into a note.
 */

export type BarcodeFormat = "qr-code" | "code128" | "ean13" | "ean8" | "upca" | "code39" | "itf14";

/** Resolve the note id from the current route, so a code can be filed into it. */
export function useCurrentNoteId(): string | null {
  const path = usePathname();
  const match = path.match(/^\/notes\/([^/]+)$/);
  return match ? match[1] : null;
}

/** Paint a QR matrix onto `canvas` with qrcode-generator (UTF-8 safe). */
function renderQrCode(
  canvas: HTMLCanvasElement,
  value: string,
  opts: { size?: number; ecc?: "L" | "M" | "Q" | "H" } = {},
): { width: number; height: number } {
  const qr = qrcode(0, opts.ecc ?? "M");
  qr.addData(value);
  qr.make();
  const count = qr.getModuleCount();
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("2D canvas context unavailable");
  const margin = 2; // 2-module quiet zone — scanners need the white border
  const target = opts.size ?? 256;
  const cell = Math.max(2, Math.floor(target / (count + margin * 2)));
  const dim = (count + margin * 2) * cell;
  canvas.width = dim;
  canvas.height = dim;
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, dim, dim);
  ctx.fillStyle = "#000000";
  for (let row = 0; row < count; row += 1) {
    for (let col = 0; col < count; col += 1) {
      if (qr.isDark(row, col)) {
        ctx.fillRect((col + margin) * cell, (row + margin) * cell, cell, cell);
      }
    }
  }
  return { width: dim, height: dim };
}

const BARCODE_FORMATS: { value: BarcodeFormat; label: string; digits: RegExp | null }[] = [
  { value: "qr-code", label: "QR Code", digits: null },
  { value: "code128", label: "Code 128", digits: null },
  { value: "ean13", label: "EAN-13", digits: /^(\d{12}|\d{13})$/ },
  { value: "ean8", label: "EAN-8", digits: /^(\d{7}|\d{8})$/ },
  { value: "upca", label: "UPC-A", digits: /^(\d{11}|\d{12})$/ },
  { value: "code39", label: "Code 39", digits: null },
  { value: "itf14", label: "ITF-14", digits: /^(\d{13}|\d{14})$/ },
];

/** Render a 1D barcode onto `canvas` via the ISO-compliant bwip-js encoder. */
async function renderBarcode(
  canvas: HTMLCanvasElement,
  format: BarcodeFormat,
  value: string,
  targetWidth = 480,
): Promise<void> {
  // `bwip-js` ships its types only on the `./browser` subpath (the top-level
  // `.` export has no `types` condition), and its browser bundle is a default
  // export object. Resolve `./browser` for types, then read `.default ?? mod`
  // so it works whether the build exposes a default or named exports.
  const mod = await import("bwip-js/browser");
  const bwipJs = (mod.default ?? mod) as unknown as {
    toSVG: (options: Record<string, unknown>) => string;
    toCanvas: (canvas: HTMLCanvasElement, options: Record<string, unknown>) => HTMLCanvasElement;
  };
  const svg = bwipJs.toSVG({ bcid: format, text: value, includetext: true });
  const m = svg.match(/viewBox="0 0\s+([\d.]+)\s+([\d.]+)"/);
  const sw = m ? parseFloat(m[1]) : 300;
  const sh = m ? parseFloat(m[2]) : 150;
  const targetHeight = Math.round((targetWidth * sh) / sw);
  // bwip-js emits viewBox but no width/height — inject both for crisp raster.
  const svgSized = svg.replace(/^<svg /, `<svg width="${targetWidth}" height="${targetHeight}" `);
  const img = new Image();
  await new Promise<void>((resolve, reject) => {
    img.onload = () => resolve();
    img.onerror = () => reject(new Error(`Could not render ${format} barcode.`));
    img.src = "data:image/svg+xml;base64," + btoa(unescape(encodeURIComponent(svgSized)));
  });
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("2D canvas context unavailable");
  canvas.width = targetWidth;
  canvas.height = targetHeight;
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, targetWidth, targetHeight);
  ctx.drawImage(img, 0, 0, targetWidth, targetHeight);
}

/** Turn a same-origin PNG data URL into a File the upload endpoint accepts. */
async function dataUrlToFile(dataUrl: string, name: string): Promise<File> {
  const blob = await (await fetch(dataUrl)).blob();
  return new File([blob], name, { type: blob.type || "image/png" });
}

/** Append the rendered code image (and the source text) to a note. */
export async function saveCodeToNote(
  dataUrl: string,
  noteId: string,
  caption: string,
  bodyText?: string,
): Promise<void> {
  const file = await dataUrlToFile(dataUrl, `${caption.replace(/[^\w.-]+/g, "_") || "code"}.png`);
  const assetId = await uploadFile(file);
  await createBlock(noteId, {
    type: "image",
    text_content: caption,
    data: { media_asset_id: assetId },
  });
  if (bodyText) {
    await createTextBlock(noteId, bodyText);
  }
}

type CodeResultProps = {
  dataUrl: string;
  value: string;
  noteId: string | null;
  caption: string;
};

/** Shared footer for anything that painted a code: result image + actions. */
function CodeResult({ dataUrl, value, noteId, caption }: CodeResultProps) {
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState<"idle" | "save" | "downloading">("idle");
  const isUrl = /^https?:\/\//i.test(value);

  async function onCopy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      /* leave the value on screen to select manually */
    }
  }
  function onDownload() {
    setBusy("downloading");
    const a = document.createElement("a");
    a.href = dataUrl;
    a.download = `${caption.replace(/[^\w.-]+/g, "_") || "code"}.png`;
    a.style.display = "none";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setBusy("idle");
  }
  async function onSaveToNote() {
    if (!noteId) return;
    setBusy("save");
    try {
      await saveCodeToNote(dataUrl, noteId, caption, value);
      setBusy("idle");
    } catch {
      setBusy("idle");
    }
  }

  return (
    <div className="qr-result">
      <img className="qr-code-image" src={dataUrl} alt={caption} />
      <div className="qr-actions">
        {value ? (
          <button className="secondary-button" onClick={() => void onCopy()} disabled={busy === "save"}>
            {copied ? "Copied" : "Copy value"}
          </button>
        ) : null}
        {isUrl ? (
          <a className="secondary-button" href={value} target="_blank" rel="noopener noreferrer">
            Open link
          </a>
        ) : null}
        <button className="secondary-button" onClick={() => void onDownload()} disabled={busy !== "idle"}>
          <Download size={14} /> {busy === "downloading" ? "Downloading…" : "Download PNG"}
        </button>
        {noteId ? (
          <button className="secondary-button" onClick={() => void onSaveToNote()} disabled={busy !== "idle"}>
            {busy === "save" ? "Saving…" : "Save to note"}
          </button>
        ) : null}
      </div>
    </div>
  );
}

function QRScanner({ onClose, noteId }: { onClose: () => void; noteId: string | null }) {
  const [value, setValue] = useState("");
  const [codeImage, setCodeImage] = useState("");
  const [error, setError] = useState("");
  const [status, setStatus] = useState<"idle" | "starting" | "scanning">("idle");
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const dupCanvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const rafRef = useRef<number | null>(null);

  const stop = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setStatus("idle");
  }, []);

  // Release the camera when the tool unmounts.
  useEffect(() => stop, [stop]);

  /** Re-encode the scanned value as a fresh QR — this is the "duplicate the code". */
  function renderDuplicate(scanned: string) {
    const canvas = dupCanvasRef.current;
    if (!canvas) return;
    try {
      renderQrCode(canvas, scanned, { size: 256 });
      setCodeImage(canvas.toDataURL("image/png"));
      setValue(scanned);
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't build the duplicate code.");
    }
  }

  /** One decode frame. Re-queues until a code is read or the user stops. */
  const tick = useCallback(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;
    if (video.readyState === video.HAVE_ENOUGH_DATA && video.videoWidth > 0) {
      const w = video.videoWidth;
      const h = video.videoHeight;
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      if (ctx) {
        try {
          ctx.drawImage(video, 0, 0, w, h);
          const frame = ctx.getImageData(0, 0, w, h);
          const code = jsQR(frame.data, w, h, { inversionAttempts: "dontInvert" });
          if (code?.data) {
            setCodeImage("");
            renderDuplicate(code.data);
            stop();
            return;
          }
        } catch {
          // Tainted-frame / read-back guard — keep scanning the next frame.
        }
      }
    }
    rafRef.current = requestAnimationFrame(tick);
  }, [stop]);

  async function startScan() {
    setError("");
    setCodeImage("");
    setValue("");
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("This browser can't open the camera. Try decoding a saved image instead.");
      return;
    }
    setStatus("starting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
      streamRef.current = stream;
      const video = videoRef.current;
      if (!video) return;
      video.srcObject = stream;
      await video.play();
      setStatus("scanning");
      rafRef.current = requestAnimationFrame(tick);
    } catch (err) {
      setStatus("idle");
      setError(err instanceof Error ? err.message : "Camera access denied. Allow the camera permission and try again.");
    }
  }

  /** Decode a saved photo — the reliable path on devices that block the camera. */
  async function decodeFile(file: File) {
    setError("");
    setCodeImage("");
    setValue("");
    stop();
    try {
      const bitmap = await createImageBitmap(file);
      const canvas = canvasRef.current;
      if (!canvas) return;
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      if (!ctx) return;
      ctx.drawImage(bitmap, 0, 0);
      const frame = ctx.getImageData(0, 0, bitmap.width, bitmap.height);
      const code = jsQR(frame.data, bitmap.width, bitmap.height, { inversionAttempts: "attemptBoth" });
      if (code?.data) renderDuplicate(code.data);
      else setError("No QR code found in that image.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't read that image.");
    }
  }

  return (
    <div className="utility-panel">
      <div className="utility-panel-header">
        <h2>QR Scanner</h2>
        <button className="icon-button" onClick={onClose} aria-label="Close">
          <X size={16} />
        </button>
      </div>
      <div className="utility-panel-body">
        <div className="qr-video-wrap">
          <video ref={videoRef} className="qr-video" playsInline muted />
          <canvas ref={canvasRef} className="qr-canvas" />
          {!codeImage && !value && (
            <p className="utility-hint">
              {status === "starting"
                ? "Starting the camera…"
                : status === "scanning"
                  ? "Scanning… point the camera at a QR code"
                  : "Point your camera at a QR code, or decode a saved image."}
            </p>
          )}
        </div>
        <div className="qr-actions">
          {status === "scanning" ? (
            <button className="secondary-button" onClick={stop}>Stop camera</button>
          ) : (
            <button className="primary-button" onClick={() => void startScan()} disabled={status === "starting"}>
              {status === "starting" ? "Starting…" : <><Camera size={14} /> Start camera</>}
            </button>
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
        {codeImage && (
          <>
            <p className="utility-hint">Scanned value (re-rendered as a fresh QR):</p>
            <CodeResult dataUrl={codeImage} value={value} noteId={noteId} caption="QR (duplicate)" />
          </>
        )}
        {/* Off-screen canvas for the duplicate render. */}
        <canvas ref={dupCanvasRef} style={{ display: "none" }} />
      </div>
    </div>
  );
}

function QRGenerator({ onClose, noteId }: { onClose: () => void; noteId: string | null }) {
  const [format, setFormat] = useState<BarcodeFormat>("qr-code");
  const [text, setText] = useState("");
  const [size, setSize] = useState(320);
  const [codeImage, setCodeImage] = useState("");
  const [error, setError] = useState("");
  const canvasRef = useRef<HTMLCanvasElement>(null);

  async function generate() {
    const value = text.trim();
    if (!value) return;
    setError("");
    setCodeImage("");
    const canvas = canvasRef.current;
    if (!canvas) return;
    const fmt = BARCODE_FORMATS.find((f) => f.value === format)!;
    if (fmt.digits && !fmt.digits.test(value)) {
      setError(`${fmt.label} expects ${fmt.digits} (digits only).`);
      return;
    }
    try {
      if (format === "qr-code") {
        renderQrCode(canvas, value, { size });
      } else {
        await renderBarcode(canvas, format, value, size);
      }
      setCodeImage(canvas.toDataURL("image/png"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not encode this value for that format.");
    }
  }

  function clear() {
    setText("");
    setCodeImage("");
    setError("");
  }

  const fmt = BARCODE_FORMATS.find((f) => f.value === format)!;

  return (
    <div className="utility-panel">
      <div className="utility-panel-header">
        <h2>QR &amp; Barcode</h2>
        <button className="icon-button" onClick={onClose} aria-label="Close">
          <X size={16} />
        </button>
      </div>
      <div className="utility-panel-body">
        <label className="qr-field">
          <span>Format</span>
          <select value={format} onChange={(e) => setFormat(e.target.value as BarcodeFormat)}>
            {BARCODE_FORMATS.map((f) => (
              <option key={f.value} value={f.value}>{f.label}</option>
            ))}
          </select>
        </label>
        <label className="qr-field">
          <span>Content</span>
          <textarea
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setCodeImage("");
            }}
            placeholder={fmt.digits ? `${fmt.label} — digits only` : "Enter text or a URL to encode…"}
            rows={4}
          />
        </label>
        <label className="qr-field">
          <span>Size: {size}px</span>
          <input
            type="range"
            min={format === "qr-code" ? 128 : 240}
            max={640}
            step={16}
            value={size}
            onChange={(e) => {
              setSize(Number(e.target.value) || 320);
              setCodeImage("");
            }}
          />
        </label>
        <div className="qr-actions">
          <button className="primary-button" onClick={() => void generate()} disabled={!text.trim()}>
            Generate
          </button>
          <button className="secondary-button" onClick={clear} disabled={!text && !codeImage}>
            Clear
          </button>
        </div>
        {error && <p className="utility-error">{error}</p>}
        {/* Kept mounted so the ref is live when generate() first runs. */}
        <canvas ref={canvasRef} className="qr-result-canvas" style={{ display: "none" }} />
        {codeImage && (
          <CodeResult dataUrl={codeImage} value={text} noteId={noteId} caption={`${fmt.label} code`} />
        )}
      </div>
    </div>
  );
}


export function UtilityBody({ id, onClose }: { id: string; onClose: () => void }) {
  const noteId = useCurrentNoteId();
  switch (id) {
    case "json": return <JsonValidator onClose={onClose} />;
    case "markdown": return <MarkdownViewer onClose={onClose} />;
    case "code": return <CodeHighlighter onClose={onClose} />;
    case "hash": return <HashTool onClose={onClose} />;
    case "qr-scanner": return <QRScanner onClose={onClose} noteId={noteId} />;
    case "qr-generator": return <QRGenerator onClose={onClose} noteId={noteId} />;
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
