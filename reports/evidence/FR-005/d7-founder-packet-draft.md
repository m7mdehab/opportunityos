# D7 — Founder acceptance packet (draft; folded into REPORT-FR-005 §9)

This is the packet the founder works through. It is written to be honest about what will not
work, because FR-004 taught that discovering a limitation yourself is worse than being told.

---

## Before you start, once

Your truth pack already exists at `private/truth_pack.yaml`. **No session in this brief read
it, wrote it, or listed that directory** — `private/**` is denied in settings, and every test
here used either `truth.fixtures` or a temporary env file generated on the spot.

```
python scripts/truth_check.py
```

This prints section names and entry counts only — never a name, employer, title, skill, or
any evidence text. Exit 0 means the pack loads and validates.

**Read the `empty sections:` line carefully, not just the `valid:` line.** The loader accepts
an unknown top-level section silently, so a mistyped heading (`certificates:` for
`certifications:`) yields a clean bill of health for a pack that is missing that block
entirely. The one place that shows up is `empty sections`. This is a known loader defect,
recorded in FR-004's next-prerequisites and still not fixed; it is not in this brief's scope.

---

## Starting the alpha

```
python scripts/alpha.py up
```

Two things changed here, and they are the reason FR-004's headline number was wrong.

`alpha.py` now uses **`opportunityos_alpha`**, creates it if absent, and **refuses to start
against any database whose name ends in `_test`** — naming the database and exiting non-zero.
It prints the database it is using, on every run:

```
PostgreSQL: using database 'opportunityos_alpha'.
Database: opportunityos_alpha (PostgreSQL 127.0.0.1:5432).
```

Under FR-004 it silently attached to `opportunityos_test` and served that database's test
fixtures — `opp-uq-*`, `example.com`, "Acme Corp" — to you as if they were real. The report
then described them as "real polled data". That is corrected in
`reports/REPORT-FR-004.md` Erratum 1.1, and D4 exists so it cannot recur.

---

## The acceptance script

The master plan's §43 lists fourteen steps; the brief refers to thirteen. All fourteen are
below — the discrepancy is recorded rather than quietly reconciled. Step 14 is longitudinal
and cannot be answered on day one.

| # | Step | Result |
|---|---|---|
| 1 | Sign in from a normal browser | |
| 2 | Open Opportunities | |
| 3 | Confirm new jobs have arrived from at least three independent source families | |
| 4 | Open a high-ranked role | |
| 5 | Verify source, canonical employer, location eligibility, match rationale, and gaps | |
| 6 | Click "Generate CV" | |
| 7 | Verify every factual claim against the Truth Graph | |
| 8 | Download/open the CV; confirm formatting and ATS-readable text | |
| 9 | Click "Open Application" | |
| 10 | Apply manually | |
| 11 | Mark applied | |
| 12 | Repeat over real opportunities | |
| 13 | Label bad matches immediately | |
| 14 | Observe whether ranking improves | |

### Then the filters, which are new

Open the **Filters** drawer on the feed. Ten filters, grouped by what they currently do:
hiding, ranking, labelling, off. **Only two hide anything by default** — your own red lines
and your excluded industries. Everything else labels or ranks.

Turn one off and watch the count move. Then use **"Show N hidden"** at the foot of the feed.

The rule this is built on, and the one to check: **a toggle changes whether a row is hidden,
ranked, or merely labelled. It never changes the decision, and it never changes the fit
score.** If you turn off `red_lines`, the red-line opportunity appears, still carrying its
real decision and the same score it always had. Nothing is being re-judged to please a toggle.

**Two blanks, and they are the point of the brief:**

> **Opportunities worth opening today: ______**
>
> **Sentences in the generated CV I would not have written: ______**

---

## What to expect, honestly

- **Step 3 should now pass.** A live poll on a clean database reached twelve sources and
  persisted real postings from remoteOK, himalayas, remotive and three Greenhouse boards —
  more than three independent families. `we_work_remotely` errored and was recorded, not
  retried. `world_bank` fetched fifteen raw records and yielded no opportunities.

- **Steps 6, 7 and 8 should now work.** This is the headline change. Under FR-004 they
  returned 409 and no document, always, by construction. Both artifacts now return a real
  DOCX for both test packs. What is *not* proven is that they work for **your** pack — no
  session here has read it, so the first genuine test of that is you. If you get a 409, the
  response names the claim and the reason, and that is the system working correctly: it is
  refusing to put a sentence in a document under your name that your evidence does not
  support.

- **Do not fix a 409 by editing your evidence to contain the generator's wording.** That
  would make the guard decorative. It is the one thing this brief treats as an automatic
  failure, and an agent was stopped mid-task for attempting it during FR-004.

- **Step 9 has no automation behind it.** "Open Application" takes you to the posting. The
  system never submits anything; marking applied records that *you* applied.

- **Step 14 needs repetition.** Nothing learns from a single session.

- **Two known engine defects you may hit, neither fixed here:** a metric whose context text
  ends in a full stop, and a number written at the very end of a sentence, can each fail to
  match their own evidence. Both are in `truth/graph.py`'s numeric matcher and the compiler's
  metric claim. If a metric-bearing claim 409s and the text looks obviously true, that is
  probably why.

If this workflow is not already easier than your current routine, the master plan's own
instruction applies: fix that before anyone builds more automation.
