# LinkedIn post

*Part 1 of three: this short post, the long-form LinkedIn article
(`content/linkedin-article.md`), and the Medium post carrying the complete executable code
(`content/medium-post.md`). ~300 words, one image (the one-order-two-boxes figure at
`docs/diagrams/grain_two_ways.png`; see the note below on the alternatives).*

---

Two reports land on your desk. One says you signed up **1,200 customers** last month. The
other says **1,000**. Same database, same afternoon — and one of them is just wrong.
Nobody in the room can tell you which.

The wrong one counted *orders* instead of *customers*: anyone who bought twice got counted
twice. It is an honest mistake, the number looks completely reasonable, and it always errs
*upward* — which is exactly why it is the one that ends up on the board slide. Nobody
re-checks a number that flatters them.

Now swap "customers" for any figure your business actually reports. Ours was **on-time
delivery**, and the same bug gave us two answers — **88.5%** or **87.3%**. Some orders
arrived in two boxes, so counting *shipments* instead of *orders* counted those orders
twice: 55 orders came in 61 boxes.

Now that a question like this gets asked in plain English and an AI hands back the answer,
the instinct is to fix it with better prompting — and prompting fixes nothing. The model
didn't misunderstand the question; it answered a perfectly reasonable one against a table
where nobody had written down what a single row is supposed to mean.

So I built the fix, and wrote up every step. The model's only job is to pick an approved
metric and fill in a small, checkable form: which metric, which filters, which dates. It
never writes SQL and never does the arithmetic — a deterministic compiler does that, from
governed metadata. Seven checks run before any SQL exists, and one refuses the
double-counted question outright instead of answering it.

The real payoff is the question a dashboard can't take: *why did it drop?* On-time delivery
fell **8.9pp** — and the obvious suspect was innocent. Transportation actually ran ahead of
plan; the delay was quality inspection, **4.75** days over a one-day standard, with no
slack to absorb it.

Full write-up, sample data, and a single file you can paste into a terminal and run — two
dependencies, no API key — in the comments.

What's your team's real answer to *"which of these two numbers is right?"* If it's "ask
Priya," you already have a semantic layer. It just isn't written down.

---

## Notes for posting

- **Image:** `docs/diagrams/grain_two_ways.png` (2600×1677) — one order shipped in two
  boxes, counted two ways to two different numbers. It states the whole problem without
  assuming any vocabulary, which is the same job the opening now does in words, and it is
  the frame that survives the feed. The pipeline swimlane `docs/diagrams/nl_dataflow.png`
  (2730×1872) is the alternative if you would rather lead with the fix than the failure; it
  carries the argument on its own for a reader who only looks at the picture.
- **Second figure — `docs/diagrams/metadata_sources.png`** (2730×1872): where each of the
  nine artifacts comes from and when it is consumed. Lead with this one instead if the
  audience is the people who *fund* metadata work rather than the people who query it —
  "only 1 of 9 artifacts is machine-harvestable" is the line that changes a budget
  conversation, and it is the honest counter to "can't we just point a catalog at it?".
  Do not post both as a carousel on the first post; a single figure gets read, two get
  skimmed. Better as the follow-up post a few days later, which also gives the first one
  a reason to resurface.
- **First comment:** the repo link plus `python src/ask.py --offline Q1`. LinkedIn
  suppresses reach on posts with outbound links in the body, which is why the link sits in
  a comment.
- **Sequencing the three parts.** Post this first; publish the LinkedIn article a day or
  two later and link it from the comments of this one; publish the Medium post
  (`content/medium-post.md`, the complete runnable file) last and link it from the
  article's closing section. Reversed, the short post has nothing left to promise. Do not
  ship all three the same day — they compete for the same readers, and the article is the
  one that needs the runway.
- **No hashtag block.** Three at most if you want them: #DataEngineering #SemanticLayer
  #DataGovernance.
- The closing question is real, not rhetorical bait — most teams genuinely do not have a
  documented answer, and the replies are the useful part of posting this.
