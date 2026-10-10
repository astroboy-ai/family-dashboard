"use client";

import { useState } from "react";
import { Braces, Hash, Search } from "lucide-react";

type Utility = {
  id: string;
  label: string;
  description: string;
  icon: React.ComponentType<{ size?: number | string; className?: string }>;
  group: string;
};

const utilities: Utility[] = [
  { id: "json", label: "JSON Validator", description: "Validate and beautify JSON", icon: Braces, group: "Developer" },
  { id: "hash", label: "Hash Tool", description: "MD5, SHA1, SHA256, etc.", icon: Hash, group: "Developer" },
];

export default function UtilitiesPage() {
  const [query, setQuery] = useState("");
  const [activeUtility, setActiveUtility] = useState<string | null>(null);

  const filtered = utilities.filter(
    (u) =>
      u.label.toLowerCase().includes(query.toLowerCase()) ||
      u.description.toLowerCase().includes(query.toLowerCase()),
  );

  return (
    <div className="page-wrap list-page">
      <section className="page-heading-row">
        <div>
          <p className="eyebrow">UTILITIES</p>
          <h1>Utilities</h1>
          <p className="page-subtitle">Handy tools for everyday tasks.</p>
        </div>
      </section>

      <label className="search-field search-page-field">
        <Search size={18} />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search utilities…"
          aria-label="Search utilities"
        />
      </label>

      <section className="list-results">
        <div className="results-meta">{filtered.length} tools</div>
        <div className="utility-grid">
          {filtered.map((u) => {
            const Icon = u.icon;
            return (
              <button
                key={u.id}
                className="utility-card"
                onClick={() => setActiveUtility(u.id)}
              >
                <span className="utility-icon"><Icon size={22} /></span>
                <span className="utility-label">{u.label}</span>
                <span className="utility-desc">{u.description}</span>
              </button>
            );
          })}
        </div>
      </section>

      {activeUtility === "json" && <JsonValidator onClose={() => setActiveUtility(null)} />}
      {activeUtility === "hash" && <HashTool onClose={() => setActiveUtility(null)} />}
    </div>
  );
}

function JsonValidator({ onClose }: { onClose: () => void }) {
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [error, setError] = useState("");

  function validate() {
    try {
      const parsed = JSON.parse(input);
      setOutput(JSON.stringify(parsed, null, 2));
      setError("");
    } catch (e) {
      setOutput("");
      setError(e instanceof Error ? e.message : "Invalid JSON");
    }
  }

  return (
    <div className="utility-panel">
      <div className="utility-panel-header">
        <h2>JSON Validator & Beautifier</h2>
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
        <button className="primary-button" onClick={validate}>Validate & Beautify</button>
        <button className="secondary-button" onClick={() => { setInput(""); setOutput(""); setError(""); }}>Clear</button>
      </div>
      {error && <p className="utility-error">{error}</p>}
      {output && <pre className="utility-output">{output}</pre>}
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
    // Hash the file's bytes, not its text: a binary upload must hash exactly
    // what is on disk, and TextEncoder would corrupt non-UTF8 content.
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
