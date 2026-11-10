# AlgebraBridge

Dynamic visual–symbolic scaffolding for algebra learning.

AlgebraBridge helps Grade 7–8 students (ages 11–14) learn to solve linear equations such as `2x + 3 = 11` and `3x − 4 = x + 6`. It puts an interactive balance scale next to a formal algebra workspace and keeps the two in sync: whatever happens on one side happens on the other. As a student shows they can work with the symbols, the scale gradually fades away. If they start making errors, it comes back.

## Quick start

```bash
npm install
npm run dev          # http://localhost:5173
npm test             # engine unit tests (parser, error classifier, fading rules)
npm run build        # type-check + production build to dist/
```

Optional telemetry collector and analytics:

```bash
npm run server                                   # Express collector on :4000
VITE_TELEMETRY_ENDPOINT=/api/telemetry npm run dev  # app POSTs each finished attempt
python3 analytics/analyze.py analytics/sample_events.json
```

Requires Node ≥ 18.18. The analytics script uses only the Python 3.9+ standard library.

## What the student sees

| Panel | Representation | Interaction |
|---|---|---|
| **Balance scale** (left) | Iconic. Violet boxes are `x`, brass weights are `+1`, red balloons are `−1`, and outlined boxes are `−x`. The pivot shows `=` when the scale is balanced and `≠` when it is tipped. | Drag blocks between the shelf and the pans, or use the `+x −x +1 −1` steppers under each pan (keyboard and touch friendly). "Share both pans into *k* groups" divides both sides. Undo. |
| **Equation** (right) | Symbolic. KaTeX renders the equation in the same colors as the blocks. The equals sign is the same balance-point badge as the scale's pivot. A ledger records each step. | **Choose a move**: pick an operation, an amount, a term, and *both sides / left only / right only*. **Write the next line**: type the next equation, as you would on paper. Hint, Restart. |

**Bidirectional sync.** If you drag a weight off the left pan, the equation changes at once to show `≠`. If you then take one off the right pan, the scale levels out and that pair of moves is recorded as a single step. If you apply "Subtract 3 from both sides" in the workspace, three blocks float off each pan. If you pick a one-sided move, the step is rejected, but the scale first tips to show what would have happened and then springs back.

## Architecture

```
src/
  engine/                     pure TypeScript, no React, unit-tested
    algebra.ts                state model, operations, parser, LaTeX/text formatting
    errors.ts                 step validation and error classification
    scaffolding.ts            fading controller, hints, level-aware feedback copy
    problems.ts               preset suite + custom-problem validation
  context/EquationContext.tsx single source of truth: store + actions (sync engine)
  telemetry/
    logger.ts                 event log (localStorage + optional POST), CSV/JSON export
    metrics.ts                per-attempt and aggregate metrics
  components/
    BalanceScale.tsx          iconic panel (framer-motion drag, steppers, tilt physics)
    SymbolicWorkspace.tsx     symbolic panel (command builder, typed entry, ledger, feedback)
    ScaffoldingController.tsx level track, streak progress, teacher override
    AnalyticsDashboard.tsx    instructor summary, charts, exports
    ProblemPicker.tsx, Math.tsx
server/index.js               Express collector → server/data/telemetry.jsonl
analytics/analyze.py          benchmarking report (text / JSON / CSV)
```

**State model.** Every equation has the form `a·x + b = c·x + d` with integer coefficients, stored as

```ts
interface EquationState {
  leftSide: { xCount: number; constants: number };
  rightSide: { xCount: number; constants: number };
  isBalanced: boolean;      // both sides equal at the true x (and a ≠ c)
  stepHistory: string[];    // LaTeX of each committed equation
}
```

Using integers is deliberate. It means every term corresponds exactly to physical blocks, so the scale and the equation always describe the same thing. Because of this, a division that would split a weight, such as `2x + 3 = 11 ÷ 2`, is treated as a premature-division error.

The store also keeps an **anchor**: the last committed balanced state. Symbolic steps are always checked against the anchor. Visual moves are allowed to unbalance the scale while the student explores. When the scale becomes level again in a new configuration, the whole sequence of moves counts as one visual step.

## Faded scaffolding

| Level | Scale | Hints and feedback | Default input |
|---|---|---|---|
| 1 Full scaffolding | Fully visible, solid blocks, color-coded equation | Concrete ("take 3 weights off **both** pans") | Choose a move |
| 2 Partial fading | Translucent wireframe | Symbolic prompts ("what is the inverse of adding 3?") | Choose a move |
| 3 Symbolic independence | Hidden (a "peek" is available and logged) | Terse self-checks ("check your signs"); equation colors removed | Write the next line |

- **Fade** one level after **3 consecutive correct symbolic steps**. Visual steps do not count toward fading, because the goal is evidence that the student can work symbolically.
- **Re-inflate** after **2 consecutive procedural errors**. Most errors move the student back one level. An asymmetric-operation error goes straight back to Level 1, because it shows a breakdown of the balance concept itself.
- Valid but unproductive steps (for example, "add 5 to both sides") don't count as successes or errors.
- Teachers can set the level manually. Analytics record these overrides but leave them out of the fade and re-inflation counts.

These thresholds are constants in `src/engine/scaffolding.ts`.

## Error classification

| Type | Typical evidence |
|---|---|
| Asymmetric Operation | A move applied to one side only. In typed entry, one side changed and the other did not. |
| Sign Error | Adding 3 to cancel a +3. A term "moved across =" without flipping its sign (`2x+3=11 → 2x=14`). An equation that one sign flip would make correct. |
| Incorrect Division | Only some terms divided (`2x+4=10 → x+4=5`), multiplied instead of divided, dividing before isolating the x-term, or dividing by 0. |
| Arithmetic Error | The right kind of operation on both sides, but a number is wrong (`2x+3=11 → 2x=7`). |
| Invalid Transformation | Anything else that isn't equivalent to the previous equation. |

Feedback names the principle that was broken, never the answer. A test checks that no hint reveals `x = n`.

## Telemetry and metrics

Each interaction is logged as an event with these fields: learner, session, attempt, problem, type, timestamp, scaffold level, source, operation, valid/productive, error type and reason, the equation before and after, and two latencies. Event types are `problem_start`, `step`, `visual_action`, `imbalance`, `hint`, `peek`, `undo`, `reset`, `scaffold_change`, `syntax_error`, and `problem_complete`.

| Metric | Definition |
|---|---|
| `step_accuracy` | valid steps ÷ attempted steps (a re-entered unchanged equation is excluded) |
| `latency_per_step_ms` | mean time between consecutive steps. The first step is timed from problem render, and `latencyFromRenderMs` is also stored on every step. |
| `error_classification` | count of steps of each error type |
| `scaffolding_dependency_score` | visual steps ÷ all steps (1 = every step made on the scale, 0 = all symbolic). Raw block manipulations are reported separately as `visualManipulations`. |

Events are saved to `localStorage`, so the app works offline. The **Instructor dashboard** tab shows KPI tiles, an error breakdown, a chart of accuracy against dependency across attempts, a table of attempts, and a live interaction trace. It exports **JSON**, **Events CSV**, and **Summary CSV**. If `VITE_TELEMETRY_ENDPOINT` is set, each finished attempt is also POSTed to the collector, and a "Sync to server" button sends any attempts that haven't been sent yet.

`analytics/analyze.py` accepts any of the export formats or the server's `.jsonl` file. It reports the same metrics per learner, broken down by **the scaffold level that was active at each step** (to check that performance holds as support fades) and by input channel. Use `--out summary.csv` for a flat per-attempt table, or `--json` for output another program can read.

## Design rationale (cognitive science)

- **Bruner's modes (enactive → iconic → symbolic).** Dragging blocks is the enactive move. The scale is the iconic model, and the equation is the symbolic form. Fading moves the student along this sequence instead of throwing them straight into symbols.
- **Dual Coding (Paivio).** The scale and the equation are two views of one state. Shared colors (violet = x, brass = constants, red = negatives) and the shared `=`/`≠` badge help students link each picture to its symbols.
- **Cognitive Load Theory.** The command builder lowers extraneous load, because the student only has to choose the inverse operation. The scale fades once it has become redundant (the expertise-reversal effect). The presets increase in element interactivity, from one-step equations to variables on both sides.
- **Relational equals sign.** The equals sign is shown as a balance point that can be tipped. This works against the misconception that "= means write the answer".

## Deployment

- **Vercel:** import the repo. `vercel.json` sets the Vite framework, `npm run build`, and the `dist` output.
- **GitHub Pages:** `.github/workflows/deploy-pages.yml` tests, builds, and deploys on every push to `main`. In the repo settings, set Pages → Source to "GitHub Actions". The build uses a relative `base`, so it works under `/<repo>/`.
- The Express collector writes to the local filesystem, so host it somewhere with persistent disk (a VM, Render, Fly.io, or similar). Static hosts and serverless functions will not keep the log.

## Limitations

- Equations must be linear with whole-number coefficients and a whole-number solution (custom problems are checked when loaded). Fractions and distribution, such as `2(x+1)`, are out of scope.
- The scale draws each block individually, so custom equations are limited to about 60 blocks.
- Drag-and-drop uses pointer events. Steppers and buttons give a full keyboard path, and the scale's state is also announced to screen readers through an `aria-live` region.
