# Running MARS locally and trying the new screens

Covers what was added on 2026-10-18: **Batch on the live API, Library, Save to library,
delete-account, Compare.** Two ways to run it. Use the first to test against the real service; use the
second when Docker is not available or you only want to see the UI states.

These screens were first checked against a stand-in API, then on the real stack on 2026-10-18
(`HANDOFF.md` §2e): create account, Predict and Batch (5 rows), Save, Library, delete, delete-account.
Not run on the real stack: a queued batch of over 1,000 molecules, because the real service takes
18 to 37 seconds per new molecule (see §2e), so 1,200 rows would take hours. Use the stand-in (B)
to see the progress bar. If a step fails, that is a finding worth reporting.

Use a browser window at least **1280 px wide**; narrower shows a "desktop workstation" notice.

---

## A. Real stack (Docker): real accounts, real database, real models

This checkout is shared by several sessions. Keep the canonical ports (API `8000`, Vite
`5173`), do not edit `.env`, `frontend/.env.local`, or the dev-server launch config (see
`AGENTS.md`, "Shared dev environment"). Check what is already running first:

```powershell
docker ps
Get-NetTCPConnection -State Listen -LocalPort 5173,8000
```

1. **Start Docker Desktop**, then from the repo root:

   ```powershell
   docker compose up -d --build        # postgres :55432, redis :6379, minio :9000, api :8000
   docker compose ps                   # wait until postgres, redis, minio and api are healthy
   curl localhost:8000/health
   ```

2. **Create the database tables.** The compose file does not run migrations, so accounts,
   Library and Save fail with "relation does not exist" until you do. From the repo root, using
   the root `.venv` (it has Alembic; the default database URL already points at
   `localhost:55432`):

   ```powershell
   cd api
   ..\.venv\Scripts\alembic upgrade head
   cd ..
   ```

3. **Start the frontend:**

   ```powershell
   cd frontend
   npm install
   npm run dev                         # http://localhost:5173
   ```

   `frontend/.env.local` must contain `VITE_API_BASE=/api` (it does on this machine; on a fresh
   clone copy `frontend/.env.example` to `.env.local` and uncomment that line). Without it the app
   runs on its illustrative fixture and Run, Save and Batch upload are off.

4. **Real predictions need promoted models.** `ml/artifacts/` is git-ignored and is mounted into
   the API container. With it present you get trained XGBoost predictions; without it every value
   is stub-served and carries the diagonal hatch (`model_id: "stub-v0"`).

To stop: `docker compose down` (keeps your data). **Do not** add `-v` unless you want the
database and MinIO volumes deleted.

---

## B. Stand-in API (no Docker): UI states only

`frontend/dev/standin-api.cjs` answers the routes these screens call and nothing else. Every
prediction is one real captured `/predict` response, repeated, so every molecule shows the same
numbers. It runs no model, database or Redis. State resets when you restart it.

Use a private port so you do not touch the shared ones:

```powershell
node frontend/dev/standin-api.cjs 18000
```

In a second terminal:

```powershell
cd frontend
$env:MARS_API_PROXY_TARGET = "http://localhost:18000"
npx vite --port 5174 --strictPort    # http://localhost:5174
```

(bash: `MARS_API_PROXY_TARGET=http://localhost:18000 npx vite --port 5174 --strictPort`.)
`VITE_API_BASE=/api` must be set, as above. The stand-in accepts any email and password at
sign-in and sign-up, and accepts the password `correct-horse` for delete-account.

---

## Sample files for Batch

Make two CSVs (any folder). The first returns directly (under 1,000 molecules), the second runs
as a queued job with live progress (over 1,000):

```powershell
python -c "open('batch_small.csv','w').write('smiles\nCCO\nc1ccccc1\nCC(=O)Oc1ccccc1C(=O)O\nnot-a-smiles\nCn1cnc2c1c(=O)n(C)c(=O)n2C\n')"
python -c "import itertools; s=itertools.cycle(['CCO','c1ccccc1','CC(=O)Oc1ccccc1C(=O)O','CCN','CCCC','bad-smiles-here']); open('batch_large.csv','w').write('smiles\n'+'\n'.join(itertools.islice(s,1200))+'\n')"
```

`not-a-smiles` and `bad-smiles-here` are there on purpose: a bad row must stay in the grid with its
error, not disappear. (With the stand-in, a file of 20 or more lines takes the queued path, so
`batch_large.csv` exercises the progress bar there too.) **On the real stack keep Batch files to a
handful of molecules**: each new molecule takes roughly 12 to 25 seconds today, and a file of up to
1,000 rows shows only "Uploading" until it finishes.

---

## A walkthrough that touches every new screen

1. **Predict, anonymous.** Open `/predict`, paste
   `Cc1ccc(-c2cc(C(F)(F)F)nn2-c2ccc(S(N)(=O)=O)cc2)cc1`, Run. All 15 rows render.
   Click **Save to library** (inspector, bottom right): you should be told saving needs an
   account, with a link, and **no form**.
2. **Create an account.** Settings (rail, bottom) → Create account → email and a password of 8+
   characters. The top bar changes from "Sign in" to your initial and "Sign out".
3. **Save a molecule.** Back in Predict, Run again, **Save to library**. The panel says it saves a
   frozen copy with the model version and that stub values are saved as stub. Add a label and tags
   (`a, A, b` is stored as `a, b`). Save. The button becomes "Saved to Library" and a second click
   cannot save it twice.
4. **Batch.** Open Batch (key 2). Choose `batch_small.csv`, Run batch. Rows appear; failed rows stay
   as rows. Select a good row → **Save molecule**; select a failed row → Save is disabled with the
   reason. **Save report** (under the upload controls) saves the whole result.
   Then choose `batch_large.csv`: you should see "Queued…", then "Running: N of 1200 (%)" with a
   bar, then Done. Switch to Predict mid-run and back; the job keeps going.
5. **Library** (key 4). Molecules and Reports tabs, newest first. Filter by label, SMILES, notes or
   tag. Select an entry: it says which model made it and when it was saved, and that it is a frozen
   copy. Delete a molecule (Delete… → Delete). Delete a report: a modal opens; Esc or Cancel closes
   it, clicking the dark backdrop does nothing.
6. **Delete account.** Settings → Delete account… → a modal lists what is removed and asks for your
   password. A wrong password keeps the dialog open and says nothing was deleted. The right one
   returns you to signed-out, and Library shows the sign-in gate with no rows left.

7. **Compare** (key 3, anonymous: no account needed). In Predict, run a molecule, then click
   **Compare molecule**: Compare opens with it in slot 1, as you typed it. Put a second SMILES in slot 2
   (optionally **Add a third molecule**) and **Run comparison**. You get one table: 15 endpoint rows in
   fixed order, one column per molecule. Nothing is ranked, highlighted or called better; out-of-domain
   cells carry an amber edge and an OOD tag but their numbers look like any other. An invalid SMILES gives
   a "Molecule rejected" message naming it and keeps what you typed. On the real service expect about 10
   seconds per new molecule.

8. **Held-out error band** (Predict). Run a molecule, select a regression row (solubility_logs, lipophilicity_logp,
   caco2_permeability, ppb_binding or clearance_microsomal). The inspector shows **Held-out error ±X** with a note saying what
   it measured, above the seed spread. Classification rows show no such row. The band comes from
   `ml/artifacts/<endpoint>/error_band.json`; if you see no band on a regression row, build them once with
   `cd ml; $env:PYTHONPATH="."; .venv\Scripts\python train\build_error_bands.py`, rebuild the API image, and use a molecule
   you have not run before (cached results from before the band existed carry none).

## What to expect that is not finished

- **Export**, Batch's **Open in Predict** and **Export row** are placeholders with no handlers.
- Password reset is not offered (no email is sent).
- A very large batch is saved as one JSON body of every row; its size and any server limit have not
  been measured.
- The saved-results `410` in `contracts/API_ROUTES.md` is not implemented by the current route.

## Tests

```powershell
cd frontend; npm test; npx tsc --noEmit; npm run lint     # 191 tests; lint has 0 errors
cd ..; .venv\Scripts\ruff check contracts api ml
.venv\Scripts\pytest contracts/tests api/tests -q          # DB/Redis tests skip unless the stack is up
```
