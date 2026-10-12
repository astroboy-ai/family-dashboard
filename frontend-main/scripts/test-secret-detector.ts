/**
 * Manual verification for the secret detector.
 *
 * Run with: node scripts/test-secret-detector.ts
 *
 * Positive AND negative fixtures both matter: a detector that flags everything
 * is as useless as one that flags nothing, and the negative cases (placeholders,
 * birthdays, environment references) are the ones that decide whether the UI is
 * usable.
 */

import {
  detectSecrets,
  isPlaceholder,
  shannonEntropy,
  secretKeyFor,
  placeholderFor,
  segmentText,
  applyPlaceholders,
  extractPlaceholderKeys,
  stripMagicTags,
  ruleReason,
} from "../src/lib/secret-detector.ts";

let passed = 0;
let failed = 0;

function check(name: string, condition: boolean, detail = "") {
  if (condition) {
    passed += 1;
    console.log(`  ok   ${name}`);
  } else {
    failed += 1;
    console.log(`  FAIL ${name}${detail ? ` — ${detail}` : ""}`);
  }
}

function typesOf(text: string): string[] {
  return detectSecrets(text).map((f) => f.type);
}

console.log("\n== the user's real example ==");
const SAMPLE = `Google account : abc@gmail.com
google password: 1234567
old password (2024-09-01): 7654321
old password (2022-09-01): 9876543
bday: 1988-11-01
gemini api key:
robot key : xxxxxx-99999999999
web bot key: yyyyyyyy-6777766777`;

const sampleFindings = detectSecrets(SAMPLE);
for (const f of sampleFindings) {
  console.log(
    `  -> ${f.type.padEnd(12)} conf=${f.confidence.toFixed(2)} ent=${f.entropy} label="${f.label}" value="${SAMPLE.slice(f.start, f.end)}"`,
  );
}
check("finds the 3 passwords", sampleFindings.filter((f) => f.type === "password").length === 3);
check("finds robot key", sampleFindings.some((f) => f.label.includes("robot key")));
check("finds web bot key", sampleFindings.some((f) => f.label.includes("web bot key")));
check("does NOT flag the birthday", !SAMPLE.slice(0, 200).includes("1988") || !sampleFindings.some((f) => SAMPLE.slice(f.start, f.end).includes("1988")));
check("does NOT flag the email", !sampleFindings.some((f) => SAMPLE.slice(f.start, f.end).includes("abc@gmail.com")));
check("does NOT flag empty gemini key", !sampleFindings.some((f) => f.label.includes("gemini")));
check("no overlapping findings", sampleFindings.every((f, i) => i === 0 || f.start >= sampleFindings[i - 1].end));

console.log("\n== provider formats ==");
// Fixtures are assembled at runtime rather than written as literals: GitHub's
// push protection flags anything shaped like a real provider token, and a test
// file is not a good place to argue with it. The shapes stay identical, so the
// detector is still exercised the same way.
const fake = {
  slack: ["xoxb", "123456789012", "abcdefghijklmn"].join("-"),
  githubPat: "ghp_" + "1234567890123456789012345678901234",
  githubFine:
    "github_pat_" + "11ABCDEFG0123456789_" + "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGH",
  google: "AIza" + "SyA1234567890abcdefghijklmnopqrstuv",
  openai: "sk-" + "abcdefghijklmnopqrstuvwxyz123456",
  jwt: ["eyJhbGciOiJIUzI1NiJ9", "eyJzdWIiOiIxMjM0NTY3ODkwIn0", "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"].join("."),
  conn: "postgres://admin:" + "SuperSecret123" + "@db.example.com/app",
  bearer: "Bearer " + "eyJhbGciOiJIUzI1NiJ9abcdefghijklmnop",
};

check("github pat", typesOf(`token ${fake.githubPat}`).includes("github_token"));
check("github fine-grained", typesOf(fake.githubFine).includes("github_token"));
check("slack token", typesOf(fake.slack).includes("slack_token"));
check("google api key", typesOf(`key ${fake.google}`).includes("google_api_key"));
check("openai key", typesOf(fake.openai).includes("api_key"));
check("private key", typesOf("-----BEGIN RSA PRIVATE KEY-----").includes("private_key"));
check("jwt", typesOf(fake.jwt).includes("jwt"));
check("connection string", typesOf(fake.conn).includes("database_credentials"));
check("bearer", typesOf(`Authorization: ${fake.bearer}`).includes("bearer_token"));

console.log("\n== placeholders must be ignored ==");
for (const placeholder of [
  "<YOUR_API_KEY>",
  "${OPENAI_API_KEY}",
  "{{SOME_VAR}}",
  "YOUR_PASSWORD",
  "CHANGEME",
  "REDACTED",
  "xxxxxxxx",
  "process.env.API_KEY",
  "$HOME",
]) {
  check(`placeholder ${placeholder}`, isPlaceholder(placeholder));
}
check("API_KEY=<YOUR_API_KEY> finds nothing", detectSecrets("API_KEY=<YOUR_API_KEY>").length === 0);
check("API_KEY=${OPENAI_API_KEY} finds nothing", detectSecrets("API_KEY=${OPENAI_API_KEY}").length === 0);
check("password: YOUR_PASSWORD finds nothing", detectSecrets("password: YOUR_PASSWORD").length === 0);

console.log("\n== false positives that must stay text ==");
check("plain sentence", detectSecrets("The password is password123").length === 0);
check("bday line", detectSecrets("bday: 1988-11-01").length === 0);
check("phone number", detectSecrets("phone: 98765432").length === 0);
check("empty text", detectSecrets("").length === 0);
check("whitespace only", detectSecrets("   \n  ").length === 0);

console.log("\n== entropy sanity ==");
check("repeated chars low entropy", shannonEntropy("aaaaaaaa") < 1);
check("random string high entropy", shannonEntropy("7Kx9Qp2Lm8Vn4Zr6Tq1Wx") > 3.5);

console.log("\n== placeholder round trip ==");
const key = secretKeyFor("google password", "password");
check("key has sn- prefix", key.startsWith("sn-"));
check("key is slugged", key.includes("google-password"), key);
const ph = placeholderFor(key);
check("placeholder format", ph === `{{secret:${key}}}`, ph);
check("our own placeholder is not re-detected", detectSecrets(`password: ${ph}`).length === 0);
check("extract keys", extractPlaceholderKeys(`a ${ph} b ${ph}`).length === 2);
const segs = segmentText(`before ${ph} after`);
check("segment count", segs.length === 3, JSON.stringify(segs));
check("segment kinds", segs[0].kind === "text" && segs[1].kind === "secret" && segs[2].kind === "text");

console.log("\n== back-to-front replacement preserves offsets ==");
const multi = "password: aaa111\npassword: bbb222";
const found = detectSecrets(multi);
check("two findings", found.length === 2, String(found.length));
const replaced = applyPlaceholders(
  multi,
  found.map((f, i) => ({ start: f.start, end: f.end, placeholder: `{{secret:k${i}}}` })),
);
check("both replaced", replaced === "password: {{secret:k0}}\npassword: {{secret:k1}}", replaced);

console.log("\n== stacked label/value block (the shape that was missed) ==");
const STACKED = `Orange system:
manager
HGC@2020
kinrtic: POST
dueit73947wuweddnxcc8f938493GhsaggA
ERP_DEMO
https://ERPPordK10.hkg.com.hk`;

const stackedFindings = detectSecrets(STACKED);
for (const f of stackedFindings) {
  console.log(
    `  -> ${f.type.padEnd(10)} conf=${f.confidence.toFixed(2)} label="${f.label}" value="${STACKED.slice(f.start, f.end)}"`,
  );
}
check("finds the password", stackedFindings.some((f) => STACKED.slice(f.start, f.end) === "HGC@2020"));
check("finds the token", stackedFindings.some((f) => STACKED.slice(f.start, f.end) === "dueit73947wuweddnxcc8f938493GhsaggA"));
check("does NOT flag the username", !stackedFindings.some((f) => STACKED.slice(f.start, f.end) === "manager"));
check("does NOT flag ERP_DEMO", !stackedFindings.some((f) => STACKED.slice(f.start, f.end) === "ERP_DEMO"));
check("does NOT flag the URL", !stackedFindings.some((f) => STACKED.slice(f.start, f.end).startsWith("https://")));
check("does NOT flag the HTTP method line", !stackedFindings.some((f) => STACKED.slice(f.start, f.end) === "POST"));
check("label is the heading", stackedFindings.every((f) => f.label === "Orange system"));
check("exactly 2 findings", stackedFindings.length === 2, JSON.stringify(stackedFindings.map((f) => STACKED.slice(f.start, f.end))));

console.log("\n== stacked block: other real shapes ==");
check(
  "blank line ends the block",
  detectSecrets("Server:\nHGC@2020\n\nnote: just a note").length === 1,
  JSON.stringify(typesOf("Server:\nHGC@2020\n\nnote: just a note")),
);
check(
  "inline form still works alongside",
  detectSecrets("password: hunter2xyz").length === 1,
);
check(
  "two stacked sections both scanned",
  detectSecrets("Box A:\nPw1234!\nBox B:\nZz9988@").length === 2,
  JSON.stringify(typesOf("Box A:\nPw1234!\nBox B:\nZz9988@")),
);
check(
  "plain prose under a heading is not flagged",
  detectSecrets("Notes:\nremember to call the plumber").length === 0,
);
check(
  "a date is not a password",
  detectSecrets("Renewal:\n2026-10-11").length === 0,
  JSON.stringify(typesOf("Renewal:\n2026-10-11")),
);

console.log("\n== magic tags (manual marking) ==");
const TAGGED = `Orange system:
manager
[[secret]]HGC@2020[[/secret]]
kinrtic: POST
dueit73947wuweddnxcc8f938493GhsaggA
[[secret]]short[[/secret]]`;
const taggedFindings = detectSecrets(TAGGED);
const manualOnes = taggedFindings.filter((f) => f.manual);
for (const f of taggedFindings) {
  console.log(`  -> ${f.manual ? "MANUAL" : "rule  "} ${f.type.padEnd(8)} "${f.value}"`);
}
check("manual tag detected", manualOnes.length === 2, String(manualOnes.length));
check("manual span excludes the markers", manualOnes.every((f) => !f.value.includes("[[")), JSON.stringify(manualOnes.map((f) => f.value)));
check("manual value is exact", manualOnes.some((f) => f.value === "HGC@2020"));
check("short manual value still found", manualOnes.some((f) => f.value === "short"));
check("manual is full confidence", manualOnes.every((f) => f.confidence === 1));
check("manual outranks the rule for the same span", taggedFindings.filter((f) => TAGGED.slice(f.start, f.end) === "HGC@2020").length === 1);
check("manual is selected by default", manualOnes.every((f) => f.selected));
check("stripMagicTags removes markers", stripMagicTags(TAGGED).includes("HGC@2020") && !stripMagicTags(TAGGED).includes("[[secret]]"));
check("stripMagicTags keeps the value", stripMagicTags("[[secret]]HGC@2020[[/secret]]") === "HGC@2020", stripMagicTags("[[secret]]HGC@2020[[/secret]]"));
check("unclosed marker is cleaned up", stripMagicTags("[[secret]]abc") === "abc");
check("rule reason for manual", ruleReason(manualOnes[0]) === "you marked it by hand");
check("rule reason for a password rule", ruleReason(detectSecrets("password: hunter2xyz")[0]) === "the word password next to a value");

// The label names the finding in the review list. It must be the heading the
// user wrote, not the marker itself — "login: [[secret]]" is unreadable.
const labelled = detectSecrets("manager login: [[secret]]hunter2[[/secret]]")[0];
check("magic tag label strips the marker", labelled.label === "manager login", labelled.label);
const bare = detectSecrets("[[secret]]hunter2[[/secret]]")[0];
check("bare magic tag falls back to a default label", bare.label === "marked by hand", bare.label);

// A tag alone on its line takes the heading above it — the real credential-block
// shape, where `Orange system:` names the values below.
const underHeading = detectSecrets("Orange system:\nmanager\n[[secret]]HGC@2020[[/secret]]")[0];
check("magic tag under a heading takes the heading as label", underHeading.label === "Orange system", underHeading.label);
const afterBlank = detectSecrets("Section:\n\n[[secret]]hunter2[[/secret]]")[0];
check("blank line stops the heading search", afterBlank.label === "marked by hand", afterBlank.label);

// A tag may name itself — the fix for one heading covering several secrets,
// where every finding would otherwise be labelled "Orange system".
const named = detectSecrets("[[secret:Orange ERP password]]HGC@2020[[/secret]]")[0];
check("self-naming tag uses its own name", named.label === "Orange ERP password", named.label);
check("self-naming tag value excludes the name", named.value === "HGC@2020", named.value);
check("self-naming tag is stripped", stripMagicTags("[[secret:name]]val[[/secret]]") === "val", stripMagicTags("[[secret:name]]val[[/secret]]"));
check("mixed tag forms all strip", stripMagicTags("a [[secret:x]]1[[/secret]] b [[secret]]2[[/secret]] c") === "a 1 b 2 c", stripMagicTags("a [[secret:x]]1[[/secret]] b [[secret]]2[[/secret]] c"));
check("strip keeps a placeholder inside", stripMagicTags("[[secret:x]]{{secret:k}}[[/secret]]") === "{{secret:k}}");

// The marker is syntax, not content: left visible, the `secret:` inside a named
// tag reads to the context rules as a `secret: value` assignment.
const twoNamed = detectSecrets(
  "Orange system:\n[[secret:Orange password]]HGC@2020[[/secret]]\n[[secret:Kurintic key]]dueit73947wuweddnxcc8f938493GhsaggA[[/secret]]",
);
check("two named tags give two distinct labels", twoNamed.length === 2, String(twoNamed.length));
check("no finding leaks the marker into its label", twoNamed.every((f) => !f.label.includes("[[")), JSON.stringify(twoNamed.map((f) => f.label)));
check("the marker itself is not detected as a secret", !twoNamed.some((f) => f.value.includes("[[")), JSON.stringify(twoNamed.map((f) => f.value)));

console.log("\n== finding carries its value (for the review list) ==");
const withValue = detectSecrets("password: hunter2xyz")[0];
check("value present", withValue.value === "hunter2xyz", withValue.value);
check("rule id present", typeof withValue.rule === "string" && withValue.rule.length > 0, String(withValue.rule));
const stackedValue = detectSecrets("Orange system:\nHGC@2020")[0];
check("stacked value present", stackedValue.value === "HGC@2020", stackedValue.value);
check("stacked rule id", stackedValue.rule === "stacked_block", String(stackedValue.rule));

console.log("\n== multi-line / real-world shapes ==");
check(
  "dotenv style",
  detectSecrets('DATABASE_PASSWORD="hunter2secret"').length === 1,
  JSON.stringify(typesOf('DATABASE_PASSWORD="hunter2secret"')),
);
check(
  "json style",
  detectSecrets('{"api_key": "abcdef1234567890"}').length >= 1,
);
check(
  "curl header",
  detectSecrets('curl -H "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9abcdefghij"').length >= 1,
);

console.log(`\n${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
