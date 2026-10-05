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
          autoFocus
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
      <button className="primary-button" onClick={validate}>Validate & Beautify</button>
      {error && <p className="utility-error">{error}</p>}
      {output && <pre className="utility-output">{output}</pre>}
    </div>
  );
}

function HashTool({ onClose }: { onClose: () => void }) {
  const [input, setInput] = useState("");
  const [hashes, setHashes] = useState<{ algorithm: string; hash: string }[]>([]);

  async function computeHashes() {
    const algorithms = ["MD5", "SHA-1", "SHA-256", "SHA-512"];
    const results: { algorithm: string; hash: string }[] = [];

    for (const algo of algorithms) {
      try {
        const encoder = new TextEncoder();
        const data = encoder.encode(input);
        const hashBuffer = await crypto.subtle.digest(algo, data);
        const hashArray = Array.from(new Uint8Array(hashBuffer));
        const hashHex = hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
        results.push({ algorithm: algo, hash: hashHex });
      } catch {
        results.push({ algorithm: algo, hash: "Error" });
      }
    }
    setHashes(results);
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
      <button className="primary-button" onClick={computeHashes}>Compute Hashes</button>
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
