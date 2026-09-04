# §9 — Founder acceptance packet (draft; folded into REPORT-FR-006)

Written to be honest about what will not work, because FR-004 taught that discovering a
limitation yourself is worse than being told about it.

---

## Before you start

Your truth pack is at `private/truth_pack.yaml`. **No session in this brief read it, wrote it, or
listed that directory.** Every test used `truth.fixtures` or the shipped synthetic template.

```
python scripts/truth_check.py
```

Prints section names and counts only — never a name, employer, title, skill or evidence text.
There is now a test that proves it: a pack with a distinctive sentinel in every field produces
output containing that sentinel zero times.

Two new optional sections your pack can carry:

- **`identity`** — name, headline, email, phone, LinkedIn, GitHub, website, city, country. This is
  why your CV had no name. Each field is an assertion with evidence, like everything else.
- **`approved_phrases`** — sentences you have written yourself. These are the **only** sentences a
  cover letter may use for motivation. If the section is absent, the letter omits the motivation
  paragraph rather than inventing one. That behaviour is tested.

`SkillRecord` also gains an optional `category`, so the CV can group your skills the way you group
them rather than in one undifferentiated list.

---

## Starting the alpha

```
python scripts/alpha.py up
```

It uses `opportunityos_alpha`, creates it if absent, refuses any database whose name ends `_test`,
and prints the database it is using on every run. Under FR-004 it silently attached to the test
database and served you fixtures as though they were real postings.

**Note for this run:** on a loaded machine `alpha.py` times out after 30 seconds waiting for the
API to listen, and rolls back cleanly. If that happens, close other work and try again. It is a
timeout, not a failure of the stack.

---

## The acceptance script

The master plan's §43 lists fourteen steps. Step 14 is longitudinal and cannot be answered on day
one.

| # | Step | Result |
|---|---|---|
| 1 | Sign in from a normal browser | |
| 2 | Open Opportunities | |
| 3 | Confirm new jobs from at least three independent source families | |
| 4 | Open a high-ranked role | |
| 5 | Verify source, employer, location eligibility, match rationale, gaps | |
| 6 | Click "Generate CV" | |
| 7 | Verify every factual claim against the Truth Graph | |
| 8 | Download and open the CV; confirm formatting and ATS-readable text | |
| 9 | Click "Open Application" | |
| 10 | Apply manually | |
| 11 | Mark applied | |
| 12 | Repeat over real opportunities | |
| 13 | Label bad matches immediately | |
| 14 | Observe whether ranking improves | |

### The three numbers this brief is judged on

> **Opportunities worth opening today: ______**
>
> **Sentences in the generated CV I would not have written: ______**
>
> **Cards where I couldn't tell where the job was or whether it was remote: ______**

The third is new, and it is the one that matters most for judging Track A. The target is zero.

---

## What changed, and what to look at

**The cards should now answer your first three questions.** Work mode, location and remote scope
are on the card, along with employment type, seniority, compensation where stated, posted age,
title family, and the source. Where a posting genuinely does not say, the card says so rather than
showing nothing — and roughly **half of real postings do not say**, which is a fact about job
boards, not about the extraction.

**Every value carries where it came from.** A work mode read from the posting's own field and one
inferred from its text are different things and the card can tell you which.

**Twenty near-identical cards should now be one.** Postings from the same employer with the same
normalized title collapse into a family carrying the best member's score, expandable, and
reversible with "show separately".

**Filters became facets.** Every extracted attribute is now something you can include or exclude,
with counts, and excluded rows are always one click away. **Nothing hides by default except your
own red lines and excluded industries.** A toggle never changes a decision or a score.

**Search works over the whole posting** — title, employer, description, requirements, location —
with phrases and negation, e.g. `pytorch -"customer engineer"`.

**The CV is a real document.** Identity block, your actual bullets, education, certifications,
projects with URLs, grouped skills, three ATS-safe templates, DOCX and PDF, with an in-browser
preview and a "what was left out and why" panel.

---

## What will not work, honestly

- **Your phone number will not appear on the CV.** The validator reads a leading `+20` as an
  unverified numeric claim and refuses it. That is a false positive, we know exactly where it is,
  and fixing it needs a change to a file this brief froze. Name, headline, email, LinkedIn, GitHub,
  website and location do appear.

- **Dates render as `2023-01-01`, not `Jan 2023`.** Rendering a month name that does not appear in
  your evidence would mean loosening the rule that every rendered word must be supported. An ISO
  date is ATS-readable. We chose the guard over the typography.

- **Source breadth grew far less than intended.** 36 new job boards were verified and registered
  against a target of 300, and **no new source is yet producing rows in the product**: Hacker News
  needs one more wiring step, and 36 registered boards have no adapter bound to them yet. Reddit,
  Upwork and most aggregators refuse automated reading, so they are registered as manual links you
  click rather than sources we poll. That is the honest state of the field, not a shortfall of
  effort.

- **About one posting in eight still lands in the `other` title family.** Mostly trades,
  cross-functional executive titles, and genuinely ambiguous ones like "Analyst".

- **`stale_postings` still hides nothing.** The code that marks a posting stale now exists, but
  nothing calls it yet.

- **Step 9 has no automation behind it.** "Open Application" opens the posting. The system never
  submits anything; marking applied records that *you* applied.

If a document refuses to generate, the panel now names the claim and the reason. That is the
system working — it is declining to put a sentence under your name that your evidence does not
support. **Do not fix a 409 by editing your evidence to contain the generator's wording.** That is
the one thing this project treats as an automatic failure.

If this workflow is not already easier than your current routine, the master plan's own instruction
applies: fix that before anyone builds more automation.
