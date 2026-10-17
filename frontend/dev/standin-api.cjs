// A UI-only stand-in for the MARS API, for trying the frontend without Docker.
//
//   node frontend/dev/standin-api.cjs [port]        (default 18000)
//   MARS_API_PROXY_TARGET=http://localhost:18000 npx vite --port 5174 --strictPort
//
// What it is: a tiny HTTP server that answers the routes the Batch, Library, Save and
// delete-account screens call. Every prediction it returns is one REAL captured /predict
// response (src/domain/real-responses/celecoxib-hit.json), repeated: it runs no model, no
// Postgres and no Redis, and every molecule gets the same numbers. It exists to exercise the
// UI states, not to produce science. State lives in memory and resets when it restarts.
//
// Accepts any email and password at sign-in and sign-up. Delete-account accepts the password
// "correct-horse" and answers 403 for any other. A batch of 20+ lines runs as a queued job
// with progress over SSE; fewer lines return directly.
const http = require("http");
const fs = require("fs");
const path = require("path");

const PORT = Number(process.argv[2] || 18000);
const FIX = path.join(__dirname, "..", "src", "domain", "real-responses");
const load = (f) => JSON.parse(fs.readFileSync(path.join(FIX, f), "utf8"));
const hit = load("celecoxib-hit.json");
const stub = load("celecoxib-stub-only.json");

let user = { user_id: "u1", email: "you@example.com" };
let signedIn = false;
const jobs = new Map();
let n = 0;
const uid = (p) => `${p}${(++n).toString(16).padStart(7, "0")}-0000-4000-8000-000000000000`;

let molecules = [
  {
    id: uid("1"), smiles: stub.smiles_standardized, label: "Stub-served example", notes: "Every value on this one came from the stub",
    tags: ["demo"], predictions_snapshot: stub, model_version: stub.model_version, created_at: "2026-10-16T09:00:00", updated_at: "2026-10-16T09:00:00",
  },
];
let reports = [];

const rows = (count) =>
  Array.from({ length: count }, (_, i) =>
    i % 7 === 3
      ? { row_index: i, smiles_input: `not-a-smiles-${i}`, ok: false, error: "Invalid SMILES (parse_error)", prediction: null }
      : { row_index: i, smiles_input: hit.smiles_input, ok: true, error: null, prediction: { ...hit, molecule_id: `mol${i}` } },
  );

function send(res, code, obj) {
  if (code === 204) {
    res.writeHead(204);
    return res.end();
  }
  res.writeHead(code, { "Content-Type": "application/json" });
  res.end(JSON.stringify(obj));
}

http
  .createServer((req, res) => {
    const url = new URL(req.url, "http://x");
    const p = url.pathname;
    const chunks = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => {
      const raw = Buffer.concat(chunks).toString("utf8");
      const json = () => {
        try {
          return JSON.parse(raw || "{}");
        } catch {
          return {};
        }
      };
      console.log(req.method, p + url.search);
      const gate = () => !signedIn && (send(res, 401, { detail: "Not authenticated" }), true);

      if (p === "/health") return send(res, 200, { status: "ok" });
      if (p === "/predict" && req.method === "POST") return send(res, 200, hit);
      if (p === "/generations") return send(res, 200, { active: hit.model_version, available: [hit.model_version] });

      if (p === "/auth/register" && req.method === "POST") return send(res, 201, { user_id: "u1" });
      if (p === "/auth/login" && req.method === "POST") {
        user = { user_id: "u1", email: json().email || user.email };
        signedIn = true;
        return send(res, 200, { user_id: "u1" });
      }
      if (p === "/auth/logout" && req.method === "POST") {
        signedIn = false;
        return send(res, 204);
      }
      if (p === "/auth/me") return signedIn ? send(res, 200, user) : send(res, 401, { detail: "Not authenticated" });

      if (p === "/batch/predict" && req.method === "POST") {
        if (gate()) return;
        const lines = (raw.match(/\n/g) || []).length;
        if (raw.includes("BOOM")) return send(res, 422, { detail: "No rows found (empty file or missing SMILES column)" });
        if (lines < 20) {
          const r = rows(Math.max(lines - 1, 1));
          return send(res, 200, { job_id: null, status: "done", total: r.length, completed: r.length, results: r });
        }
        const id = uid("a");
        jobs.set(id, { total: lines - 1 });
        return send(res, 200, { job_id: id, status: "queued", total: lines - 1, completed: 0, results: null });
      }
      let m;
      if ((m = p.match(/^\/batch\/progress\/(.+)$/))) {
        if (gate()) return;
        const job = jobs.get(m[1]);
        if (!job) return send(res, 404, { detail: "Not found" });
        res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" });
        let step = 0;
        const t = setInterval(() => {
          step += 1;
          const done = step >= 6;
          const completed = done ? job.total : Math.floor((job.total * step) / 6);
          const status = done ? "done" : step === 1 ? "queued" : "running";
          res.write(`data: ${JSON.stringify({ job_id: m[1], status, total: job.total, completed })}\n\n`);
          if (done) {
            clearInterval(t);
            res.end();
          }
        }, 500);
        req.on("close", () => clearInterval(t));
        return;
      }
      if ((m = p.match(/^\/batch\/results\/(.+)$/))) {
        if (gate()) return;
        const job = jobs.get(m[1]);
        if (!job) return send(res, 404, { detail: "Not found" });
        const r = rows(job.total);
        return send(res, 200, { job_id: m[1], status: "done", total: r.length, completed: r.length, results: r });
      }

      if (p === "/molecules" && req.method === "GET") return gate() || send(res, 200, molecules);
      if (p === "/reports" && req.method === "GET") return gate() || send(res, 200, reports);
      if (p === "/molecules/save" && req.method === "POST") {
        if (gate()) return;
        const b = json();
        const row = {
          id: uid("2"), smiles: b.prediction.smiles_standardized, label: b.label ?? null, notes: b.notes ?? null, tags: b.tags ?? [],
          predictions_snapshot: b.prediction, model_version: b.prediction.model_version, created_at: new Date().toISOString().slice(0, 19), updated_at: new Date().toISOString().slice(0, 19),
        };
        molecules.unshift(row);
        return send(res, 201, row);
      }
      if (p === "/reports/save" && req.method === "POST") {
        if (gate()) return;
        const b = json();
        const row = {
          id: uid("3"), type: b.type, source_batch_job_id: b.source_batch_job_id ?? null, results_snapshot: b.results,
          molecule_ids: b.molecule_ids ?? [], notes: b.notes ?? null, tags: b.tags ?? [], created_at: new Date().toISOString().slice(0, 19),
        };
        reports.unshift(row);
        return send(res, 201, row);
      }
      if ((m = p.match(/^\/molecules\/(.+)$/)) && req.method === "DELETE") {
        if (gate()) return;
        const before = molecules.length;
        molecules = molecules.filter((x) => x.id !== m[1]);
        return molecules.length === before ? send(res, 404, { detail: "Not found" }) : send(res, 204);
      }
      if ((m = p.match(/^\/reports\/(.+)$/)) && req.method === "DELETE") {
        if (gate()) return;
        const before = reports.length;
        reports = reports.filter((x) => x.id !== m[1]);
        return reports.length === before ? send(res, 404, { detail: "Not found" }) : send(res, 204);
      }
      if (p === "/account" && req.method === "DELETE") {
        if (gate()) return;
        if (json().password !== "correct-horse") return send(res, 403, { detail: "Incorrect password" });
        signedIn = false;
        molecules = [];
        reports = [];
        return send(res, 204);
      }
      send(res, 404, { detail: `Not found: ${p}` });
    });
  })
  .listen(PORT, () => console.log(`MARS UI stand-in API on http://localhost:${PORT} (no model, no database)`));
