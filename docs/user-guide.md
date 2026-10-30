# FOX MLO — User guide

For project managers who create and follow translation orders. FOX MLO takes posts and pages from a WordPress site (Polylang), sends them through Plunet for translation and review, checks the result, and puts the translations back on the site.

> **Status (October 2026):** the backend described here is complete. Until the interface is connected to it (phase 6), the web app runs on **demo data**: a **DEMO DATA** badge shows in the header and everything resets when you reload the page. The screens and buttons are the same; only the data is simulated.

---

## 1. Key ideas

| Term | Meaning | In Plunet |
|---|---|---|
| **Order** | Work the customer has confirmed. Its workflows start at once. | Auftrag |
| **Quote** | A price proposal. Nothing runs until the customer accepts it. | Angebot |
| **Position** | One post (or page) in one target language, with its own `.xliff` file. 2 posts × 3 languages = 6 positions. | Item |
| **Workflow** | The chain of tasks a position goes through. | — |
| **Task** | One step of the workflow. | A job, for tasks done by people |

**Tasks**

| Task | Done by | What happens |
|---|---|---|
| **Import** | FOX MLO | Gets the `.xliff` from Polylang, counts words and segments, attaches the file to the Plunet item. |
| **PM** | A person, in Plunet | Project management job (`PRM` in Plunet): preparation, assignment, checks. |
| **Translation** | A person, in Plunet | Translation job (`TRA`). |
| **Review** | A person, in Plunet | Review job (`REV`). |
| **QA** | FOX MLO | Automatic checks on the translated file (section 8). |
| **Deliver** | FOX MLO | Sends the translation where you chose (section 3, step 3). |

**Templates** decide which tasks a position has:

| Template | Tasks | For |
|---|---|---|
| Standard | Import → PM → Translation → Review → QA → Deliver | Web content (default) |
| Light | Import → Translation → QA → Deliver | Short, low-risk content |
| Regulated | Import → PM → Translation → Review → Review → QA → Deliver | Legal and compliance texts |

### Who does what

- **People work in Plunet**, as they do today: the PM assigns jobs, translators and reviewers deliver there.
- **FOX MLO organises the work**: it creates the order, items and jobs in Plunet, starts each task when the previous one is done, runs the automatic steps, and shows everything in one place.
- **Plunet is the reference.** When FOX MLO changes something (creates, cancels, restarts), it does it in Plunet first.
- **FOX MLO checks Plunet every 2 minutes.** A job delivered in Plunet shows as done in FOX MLO within about 2 minutes.

---

## 2. Getting around

The header has three links: **Orders**, **Analytics** and **ETL (v1)** (the old screens, kept for now).

- **Language:** switch between English and French in the header. Your choice is remembered.
- **Service status:** a dot in the header. Green with "Plunet · Polylang · Temporal online" means all is well. Orange with "Some services are unavailable" means one service is down; see section 10.
- **Live updates:** order and workflow pages update by themselves (marked **LIVE**). You do not need to reload.

---

## 3. Create an order or a quote

**Orders → New order.** The form has four steps; you can go back at any time.

**Step 1 · Basics**
- **Type:** *Order* (workflows start at once) or *Quote* (nothing runs until it is accepted).
- **Title:** free text, shown in lists and in Plunet.
- **Customer** and **Project manager:** taken from Plunet (active customers, internal resources). New entries in Plunet appear within 10 minutes.
- **Deadline:** used as the due date of every Plunet job. After it, the order is marked **OVERDUE** and the workflow log gets a warning.

**Step 2 · Source**
- **WordPress site** and **Source language.**
- **Posts & pages:** tick the ones to translate. Each one shows its word count and the languages it already has ("has fr, de-at"). If you choose a language a post already has, the delivery updates that existing translation.
- **Target languages:** tick one or more. The form shows how many positions will be created (posts × languages).

**Step 3 · Workflow**
- **Workflow template:** applies to every position (see the table above).
- **Return trip** — where translations go:
  - **Back to Polylang** (default): creates or updates the translated post, linked to the source post. It is saved as a **draft** in WordPress: publish it there when ready.
  - **Other endpoint:** sends the translated `.xliff` to a URL you enter.
  - **None · download only:** nothing is sent; download the file from the position's **File** tab.

**Step 4 · Review** — check the summary and click **Create order & start workflows** (or **Create quote in Plunet**).

What happens next:
1. FOX MLO creates the order (or quote) in Plunet, with one item per position.
2. Each `.xliff` is imported from Polylang and attached to its Plunet item.
3. For an order, each position starts its workflow. For a quote, nothing runs yet.

If something is wrong (a post no longer exists in the source language, an unknown language…), the form shows the reason and nothing is created.

---

## 4. Quotes

A quote shows **Awaiting acceptance** and the banner "No workflow runs on a quote".

**When the customer accepts**, either:
- click **Accept → convert to order** on the quote page, **or**
- set the quote to *Accepted* in Plunet. FOX MLO picks this up within 2 minutes.

Then **the PM converts the quote into an order in Plunet** (Plunet does not allow FOX MLO to do this step). FOX MLO detects the new order within 2 minutes, takes its number, links each position to its item, and starts the workflows. Until then the quote stays in *Awaiting acceptance*; its activity feed says it is waiting for the conversion.

**When the customer declines:** click **Reject** in FOX MLO, or reject, cancel or let the quote expire in Plunet. The quote becomes **Rejected** and nothing runs.

> Do not remove the `FOX-P…` code from the item descriptions in Plunet (for example "P01 · Spring collection · FOX-P412"). FOX MLO uses it to find the items again after the conversion.

---

## 5. The orders list

**KPIs** at the top: running workflows, tasks waiting on people, failed workflows, quotes pending.

**Filters:** type (orders, quotes, needs attention), project manager, customer, and a search on number, title or customer.

**Columns**
- **Status:** Draft, Awaiting acceptance, Running, **Needs attention** (at least one position failed or is paused), Completed, Cancelled, Rejected.
- **Positions:** one coloured segment per position — completed, running, waiting on a person, paused, failed, not started — and "3/5 completed".
- **Deadline:** with **OVERDUE** once passed.
- **Last activity:** the latest event of the order.

Tip: the **Needs attention** filter shows everything that waits on you: failures, paused positions and late orders.

---

## 6. An order

**Header:** number, title, status, and the buttons:
- **Pause all** — pauses every running or waiting position.
- **Resume all** — resumes every paused position.
- **Retry failed · n** — retries the failed task of every failed position.
- **Open in Plunet ↗** — the order (or quote) in Plunet.

**Details:** customer, PM, deadline, template, return trip, source.

**Positions:** one row per position with its language pair, task chips (done, current, failed…), a one-line note ("Translation assigned to A. Laurent in Plunet", "QA failed: 1 blocking finding", "Delivered to Polylang as post #512") and **Open workflow**.

**This order:** elapsed time, words, **cost to date** (sum of the Plunet job prices), errors.

**Recent activity:** the latest events, live.

The order is **Completed** when every position is completed or cancelled, and **Cancelled** when all positions are cancelled.

---

## 7. A position's workflow

Open a position from its order. The page shows the title, `source → target`, the Polylang post, the Plunet item, the template, the return trip, and a **banner** that says what is going on and what you can do.

### Controls

Only the actions that make sense are shown:

| Workflow state | Buttons |
|---|---|
| Running, Waiting | Pause · Cancel |
| Paused | Resume · Restart from… · Cancel |
| Failed | Retry · Restart from… · Cancel |
| Completed | Restart from… |
| Not started (quote), Cancelled | — |

- **Pause** — the current task finishes, but no new task starts. **Jobs already given to people continue in Plunet**; when they are delivered, the workflow waits for you before going on.
- **Resume** — the workflow goes on from where it stopped.
- **Retry** — runs the failed task again. For a task done in Plunet, a **new** job is created.
- **Restart from…** — choose a task: it and every task after it run again; earlier results are kept. An open Plunet job is cancelled first, and new jobs are created for the people tasks. On a completed position this starts a new run (useful to re-check or re-deliver). A reason is optional and goes to the log.
- **Cancel** — final. Unfinished tasks stop, their Plunet jobs and the item are set to *Canceled*, completed work is kept. **A reason is required.** If Plunet cannot be updated, the position is still cancelled and the log asks you to check Plunet by hand.

If an action is not possible at that moment (someone else just paused it, the workflow has moved on), FOX MLO shows the reason and nothing changes.

### Tabs

- **Overview** — every task with its state, the Plunet job number and status, assignee, duration, attempts, and cost.
- **Logs** — the full history: state changes, warnings and errors, and user actions with who did them and why. Filter: all, errors & warnings, state changes, user actions.
- **Analytics** — elapsed time, cost, errors, words; time per task; QA findings.
- **File** — each segment side by side (source and target) with its QA result, and the `.xliff` download (as imported, or as translated).

### Task states and Plunet job status

For tasks done in Plunet, FOX MLO shows the Plunet job status as it is, and derives its own state from it:

| Plunet job status | FOX MLO |
|---|---|
| In preparation | Pending |
| Requested, Assigned – waiting | Waiting (on a person) |
| In progress | Running |
| Delivered, Approved (and invoice states) | Done |
| Canceled | The task **fails** — retry it to create a new job, or cancel the position |

A job past the deadline adds one warning in the log ("overdue"); the workflow keeps waiting.

---

## 8. Working in Plunet

For the PM and the linguists, nothing changes in how they work:

1. FOX MLO creates the job (`PRM`, `TRA` or `REV`) on the item when its turn comes, with a start date of today and the order deadline as due date, and no resource yet.
2. The PM assigns a resource and sets the price in Plunet as usual.
3. The linguist works and **delivers the translated `.xliff` in the job's output folder**, then sets the job to *Delivered*.
4. Within 2 minutes FOX MLO sees it, records the cost and the assignee, and starts the next task.

**About the translated file:** QA takes the `.xliff` from the output folder of the **last delivered job** (the review if there is one, else the translation). If several `.xliff` files are there, it prefers the one named like the original (e.g. `p412.fr.xlf`). Without any `.xliff` in the output folder, QA fails with "No translated .xliff in the output folder".

**Do not** delete items or jobs that FOX MLO created; cancel the position in FOX MLO instead, so both systems stay in step.

---

## 9. QA checks

QA runs on every segment of the translated file.

**Blocking** (QA fails, the workflow stops and waits for you):
- empty or missing translation;
- placeholders differ from the source (`{0}`, `{name}`, `%s`, `%1$s`, `%d`);
- inline tags differ or are broken;
- the translation is not valid XML.

**Warnings** (shown, the workflow continues):
- translation identical to the source (more than 3 words);
- numbers differ;
- much longer than the source, or over the length limit in the file;
- extra spaces at the start or end, double spaces.

**When QA fails:** the banner names the segments (e.g. `u-002`); the **File** tab shows each finding next to the segment. Then either:
- have the linguist correct the file in the output folder of their job in Plunet, and click **Retry QA**; or
- **Restart from…** the review (or translation): a new job is created for a fresh pass.

---

## 10. Analytics

**Analytics** in the header: per **project manager** or per **customer**, over all orders (quotes are not counted):

| Column | Meaning |
|---|---|
| Orders, Positions | How many |
| Completed | Completed positions |
| Avg. duration | From the start of a position's first task to the end of its last one, completed positions only |
| Cost | Sum of the Plunet job prices |
| Errors | Error events (failed tasks, failed checks) |

Costs are shown in the currency most jobs are priced in. Jobs priced in another currency are left out of that total.

---

## 11. Troubleshooting

| You see | What to do |
|---|---|
| A task stays *Waiting* | Someone has to act in Plunet: check the job's assignment and status. FOX MLO only moves on when Plunet says *Delivered*. |
| Delivered in Plunet but not done in FOX MLO | Wait up to 2 minutes. If it still does not move, check that the job in Plunet is really *Delivered* (not only the file uploaded). |
| "QA failed: n blocking finding(s)" | Section 9. |
| "No translated .xliff in the output folder" | The linguist delivered without a file, or in another folder. Add the `.xliff` to the job's output folder, then **Retry QA**. |
| "Plunet job J-… was cancelled in Plunet" | Someone cancelled the job in Plunet. **Retry** creates a new job; **Cancel** stops the position. |
| A quote stays *Awaiting acceptance* after acceptance | The PM still has to convert it into an order in Plunet. |
| A button answers with a message instead of acting | The workflow changed state in the meantime (another user, or Plunet). The message says why; the page already shows the current state, so check it before trying again. |
| "Some services are unavailable" | One of Plunet, Polylang or the workflow engine cannot be reached. Running work is not lost: it continues by itself when the service is back. Tell your administrator if it lasts. |
| Delivery failed with Polylang or the endpoint | The site refused or was down. Automatic retries happen first; if the task fails, **Retry** once the site works again. |

---

## 12. Not available yet

- Signing in. Until then, actions are logged under the name the interface sends, or "anonymous".
- Changing the task list of a single position after creation (the wizard mentions it; it is planned).
- Assigning a linguist from FOX MLO: assign in Plunet.
- A real WordPress site: the current setup uses a built-in copy of a Polylang site for testing.
