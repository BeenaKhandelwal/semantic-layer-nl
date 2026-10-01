# Publishing checklist — the Medium post

Working notes, deliberately **not** part of `medium-post.md`. Publishing instructions
inside the published article are the clearest sign nobody read it as a reader.

---

## Title and subtitle

Shipped as:

- **Title:** `87.3% or 88.5%? Your LLM Can't Tell — and It Will Pick the Flattering One`
- **Subtitle:** `A governed semantic layer that refuses the wrong number — complete,
  executable Python, two dependencies, no API key.`

Medium treats the first H1 as the title and the following H2 as the subtitle when you
import from a file (`medium.com/p/import`) or paste. Check both landed in the right slots
before publishing — pasted markdown sometimes arrives as two H1s, and a subtitle demoted
to body text loses the search snippet.

Two swaps if the first framing underperforms:

| Alternative title | Trade |
|---|---|
| `Your LLM Writes Valid SQL and Still Returns the Wrong Number` | Broader hook, no numbers — better on social, weaker in search |
| `The Metadata Field That Decides Whether an LLM's Answer Is Right` | Best for search on "metadata"; slower to the point |
| `Why Did On-Time Delivery Drop? Text-to-SQL Can't Say, and That's a Metadata Bug` | Leads with the diagnostic section — the part no BI tool can do — instead of the two numbers. Strongest if the first framing underperforms; costs the numeric hook |
| `87.3% or 88.5%? Text-to-SQL Can't Tell, and That's a Metadata Bug` | The previous shipped title. Best search coverage of the four — `text-to-SQL` and `metadata` both in the title — and the flattest read in a feed. Swap back if search traffic matters more than the click-through |

The shipped title carries `LLM` and the subtitle carries `semantic layer`. `Text-to-SQL`
and `natural-language querying` are left to the tags, the TL;DR and the body, which is a
deliberate trade: the title's job is the click, the tags carry the search.

The title went through one revision. It used to end `...Text-to-SQL Can't Tell, and That's a
Metadata Bug` — accurate, and it read like an internal memo. `and It Will Pick the
Flattering One` is the same claim with the consequence attached, and the consequence is the
part people quote. The subtitle did not change with it — it states what the reader
gets, which is the job the title no longer does. The em-dash clause is also the post's
actual argument: the error is not
random, it errs upward, and that is why it survives review. Keep the numbers at the front —
they are what makes the headline specific rather than another "your AI is lying to you"
post.

## Tags

Five, first one weighted most heavily: **Data Engineering**, **Analytics**, **LLM**,
**Data Governance**, **SQL**.

## Images

| Where | File | Note |
|---|---|---|
| Header | `docs/diagrams/grain_two_ways.png` (2600×1677) | The lead image, and the one that has to survive the feed: it states the whole problem without assuming any vocabulary. Upload the PNG; Medium's SVG support is unreliable. |
| "The rule everything else follows from" | `docs/diagrams/nl_dataflow.png` (2730×1872) | The six stages. Was the lead image and lost that slot deliberately — a pipeline diagram means nothing until the reader accepts the premise. |
| "The metadata: the fields no crawler emits" | `docs/diagrams/metadata_sources.png` (2730×1872) | The figure that answers "can't we just harvest it from SAP?" |

All three are generated — `render_grain.py`, `render_dataflow.py`, `render_sources.py` — so
re-render before uploading if the code has moved. Each takes `--check` and exits non-zero
when the committed figure is stale.

Caption all three — Medium's curators look for it, and an uncaptioned diagram in a
technical post reads as decoration.

## The complete file

The post carries the whole 1,000-plus-line file in one fence, on purpose: the promise is
that a reader can copy it out of the post and run it. That fence is byte-identical to
`standalone/semantic_layer_demo.py`, which `tests/test_standalone.py` executes.

If it reads as too much to scroll, the idiomatic Medium move is a **Gist**: paste the Gist
URL on its own line and Medium expands it inline. Do it as an *addition* — put the Gist
above the fence rather than replacing it — because a Gist is a dead end for anyone reading
on a train with no signal.

Do not hand-edit the fence, or the post and the tested file stop being the same program.
Regenerate instead:

```bash
python content/build_medium_post.py          # rewrites content/medium-post.md
python content/build_medium_post.py --check  # exits 1 if the post on disk is stale
```

## Canonical URL

The LinkedIn article and this post make the same argument. Pick one canonical and set the
other to point at it in Medium's story settings, or the two compete in search and both
rank lower.

## Sequencing with parts 1 and 2

1. `linkedin-post.md` — the short post, first.
2. `linkedin-article.md` — a day or two later, linked from the first post's comments.
3. `medium-post.md` — last, linked from the article's closing section.

Reversed, the short post has nothing left to promise. Do not ship all three the same day;
they compete for the same readers and the article needs the runway.

Replace the three prose references in *"Where the rest of it lives"* with real links once
parts 1 and 2 are live — they are deliberately written as descriptions, not URLs, so the
file has no dead placeholder in it.

## The two audiences

The post opens plain-English — a courier story, three orders counted by hand, and a
five-word glossary — before any YAML appears. That is deliberate. The argument does not
need SQL to land, and a reader who bounces at the first code fence never reaches the part
that would have convinced them.

Do not cut that section to shorten the post, and do not move it below the TL;DR. The
technical reader is handled by its first line, which tells them to skip it.

## If it has to be cut for length

Cut *"The intent"* and *"The compiler"* and keep *"Why it dropped"*. Descriptive querying
is a demo; diagnostic querying is the argument. The diagnostic section is also the only
part of the post that no BI tool can do, which is what makes it the section worth reading.

**Do not cut *"What this file honestly does not do"***, even though it is the easiest
19 lines to lose. A post arguing that overclaiming is the root problem cannot itself
overclaim, and the section is what earns the rest of it the benefit of the doubt. The
same goes for the full provenance block under *"The governed answer"* — it is long, and
being long is the point: every line of it is a question somebody asks in the meeting.

## Pre-flight

- [ ] `python content/build_medium_post.py --check` says the post is current
- [ ] `python -m pytest tests/test_content.py tests/test_standalone.py -q` green
- [ ] the code fence pastes into a clean file and runs on `pip install duckdb pyyaml`
- [ ] all three figures uploaded, captioned, and right-side-up at Medium's width
- [ ] the lead image is `grain_two_ways.png` — that is what the feed shows
- [ ] title in the title slot, subtitle in the subtitle slot
- [ ] five tags, canonical URL decided
- [ ] first response ready: the repo link (Medium does not penalise outbound links the way
      LinkedIn does, so the repo link can also sit in the body)
