# Model options

**Update, November 26, 2026:** market research and automatic pricing were removed from the app, so the research
sections below are background only. Claude is still used for photo ID and listing text.

Findings from the chat on November 24, 2026: whether to use Claude for market research, and whether free models could replace it.

**Nothing here was tested on real photos or live listings.** No model was run. Quality and cost figures marked "guess" are judgments
from reading the code. Items marked † were added or checked against the code when this file was written.

## Summary

- **Market research:** use non-AI sources as the base. Use a model to read sold results you paste in, not to find prices on its own.
- **Free models:** no free option is proven to match Claude on both jobs. They are worth testing for photo ID. For research, the limit
  is access to sold prices, which a different model does not fix.
- **Dropping AI from research does not remove the need for a model:** photo ID uses one too. Listing text can fall back to a template.

## Where Claude is used today

| Part | Uses Claude? | Code |
|---|---|---|
| Photo ID | Yes | `lister/identify.py` |
| Listing text | Yes, with a template fallback | `lister/drafting.py` |
| Reading pasted 130point, Collectr, Terapeak or eBay results | Yes | `lister/research/pasted.py` |
| Web search for prices | Yes | `lister/research/websearch.py` |
| eBay active, eBay sold, PriceCharting, TCGdex | No | `lister/research/sources.py` |
| Deciding which comps match, and setting the price | No | `lister/research/matching.py`, `lister/pricing.py` |

Claude does not choose the price, but it can supply the numbers behind it.

## Market research: Claude or no AI

### With Claude

Pros:
- **Possible sold prices.** It is the only automatic route to them unless eBay has granted you its sold-data API, which is closed to
  new applicants.
- **Less upkeep.** It copes with messy titles and layout changes, with no parser per site.
- **Faster pasting.** It turns a pasted page into rows. A price is rejected unless that number appears in the paste
  (`pasted.py:45-47`). † Any number in the paste counts, including a year or card number, and titles and dates are not checked.

Cons:
- **Weak price check on web search.** The code confirms Claude saw the page's URL, not that the price was on it
  (`websearch.py:86-89`). A misread price on a real page gets through.
- **Its labels are trusted.** It reports the title, date and sold/asking status. If it adds "TAG 10" to a title, the matcher accepts it.
- **Possible double counting.** A sale with a slightly different title or date, or a PriceCharting value found by two routes, can
  count twice.
- **Inconsistent.** The same card can return different comps on different runs.
- **Limited access.** 130point blocks scripts, and other sites may block Claude too.
- **Cost and speed (guess).** $0.30–$1.50 per item for research on Opus 5.5, and likely the slowest source. Reading one paste should
  cost a few cents.

### Without AI

Pros:
- **Traceable and repeatable.** The same data gives the same price, and each number has a named source.
- **Cheap and fast.** TCGdex and eBay active have no per-item AI cost. PriceCharting needs a paid token.
- **Fails visibly.** A broken source shows an error instead of a plausible wrong price.

Cons:
- **Poor coverage for slabs.** TCGdex prices only ungraded Pokémon cards. With no keys, a slab gets no market value.
- **Mostly asking prices and guides.** With fewer than three sales, confidence stays low.
- **More manual work.** Type sales in one at a time (already supported) or build a parser per site.
- **Rigid matching.** Unusual titles can be wrongly excluded, although you can tick them back on.

## Free models

| Job | Best free option | Likely result | Catch |
|---|---|---|---|
| Photo ID, hosted | Gemini Flash free tier, e.g. Gemini 3.8 Flash | Probably close on clear slab labels | Google uses free-tier content to improve its products |
| Photo ID, private | Qwen3-VL on this Mac | Good at label text; less certain on variants, condition and grouping | Slower, with more to correct by hand |
| Reading pasted sales | Qwen3-VL on this Mac | Good fit, since prices not in the paste are rejected | Titles and dates are not checked that way |
| Automatic price search | Free model plus a search API such as Tavily | Probably worse than Claude, which is already limited here | More code to build, same blocked sites |

### Gemini (hosted, not open source)

Best use here: photo ID. Reading pasted sales is also possible. "Read" means quoted from Google's page; "summary" means it came from
an automatic summary of the page or a search, and is unconfirmed.

| | Detail | Basis |
|---|---|---|
| Free text/vision models | `gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3.5-flash-lite`, `gemini-4-hydrogen` | Read |
| Also listed as free | `gemini-3.1-flash-lite`, `gemini-3-flash-preview`, `gemini-2.5-flash`, `gemini-2.5-flash-lite`, `gemini-2.5-pro` (described as deprecated) | Summary |
| Not free | `gemini-4-carbon` | Read |
| Also listed as not free | `gemini-4-argon`, `gemini-4-neon`, `gemini-3.1-pro-preview` | Reported by the fetch, exact wording not kept |
| Photo input | Free on the free-tier models | Summary |
| Privacy | Free tier: "Content used to improve our products". Paid tier: not used | Read |
| Request limits | Not published for text and vision models; AI Studio shows yours. Limits are per project, not per key, and daily quotas reset at midnight Pacific | Read |
| Google Search, Gemini 3 and newer | "Not available" on the free tier | Read |
| Google Search, Gemini 2.5 Flash and Flash-Lite | 500 free searches a day, shared between the two | Summary |
| Reading a given URL (URL context) | Free on the free tier, charged as input tokens elsewhere | Summary |
| Cheapest paid vision model | `gemini-2.5-flash-lite`, $0.10 input and $0.40 output per million tokens | Summary |
| `gemini-3.5-flash-lite`, paid | $0.30 input per million tokens for text, image, video or audio | Read |

- **Volume:** the photo set was 19 JPGs (since removed from `photos/`), so free limits may not be a problem.
- **Search conflict:** the pricing page also mentions 5,000 free search requests a month for Gemini 3 and newer. That appears to be for
  paid accounts, since the free tier says "Not available". Forum posts disagree.
- **Privacy:** the app removes GPS and other metadata first, but the photos, cert numbers and pasted text would still reach Google under
  the free-tier terms.

### Qwen3-VL (open-weight, runs on this Mac)

Best use here: private photo ID, and reading pasted sales. Nothing is sent to a provider and there is no per-item charge. All model
claims below come from search summaries of third-party guides, so treat them as leads.

| Size | What the guides said | On this Mac (M3 Pro, 36 GB memory, 46 GB free disk) |
|---|---|---|
| Qwen3-VL 8B | Called the best local vision model for most people; one guide pairs it with 16 GB Macs | Should run comfortably. Start here |
| Qwen3-VL 32B | Recommended for 24 GB graphics cards; praised for reading text in images | Should fit at 4-bit compression, more slowly. Check memory for long inputs |
| A newer Qwen 27B (Qwen3.8-27B in some results) | Vision model released August 2026. Sources are unclear on the version; one states an Apache 2.0 licence | Should fit at 4-bit compression, more slowly |

- **Strengths expected:** label text, and turning a paste into rows, where the existing check rejects prices that are not in the paste.
- **Weaknesses expected:** variants, ungraded condition and grouping, so more to correct by hand.
- **Evidence:** no reliable independent test on cards was found, and no guide gave a clear text-reading comparison of Qwen against Gemma.
- **Setup:** a local runner is needed. Ollama, LM Studio and llama-server were not found when the chat checked.

Other open-weight models that turned up, if Qwen does badly:

| Model | What was said |
|---|---|
| Gemma 4 (27B and 31B named in different sources) | One local text-reading guide's top pick, with little detail |
| Qwen3.6-35B-A3B | Listed in a Mac comparison |
| MiniCPM-V 4.7 35B-A3B | Said to lead on documents and text reading, but by its vendor's own comparison |

### Others

- **OpenRouter:** free models are capped at 50 requests a day, and the models available change.
- **Tavily:** about 1,000 free search credits a month. It still depends on which sites it can reach.

### Where free models are likeliest to slip

- **Small text:** cert numbers and card numbers.
- **Variants:** reverse holo, 1st Edition, or pristine versus gem mint.
- **Grouping:** the two identical Charmanders and their reports.
- **Ungraded condition:** where an overconfident answer costs money.

A wrong card number or grade also pulls in the wrong comps.

## Cheaper Claude models

Standard API prices, USD per million tokens, from Claude Code's bundled API reference on November 24, 2026:

| Model | Input | Output | Price next to Opus 5.5 |
|---|---|---|---|
| `claude-opus-5-5` (current default) | $4.00 | $20.00 | |
| `claude-sonnet-5-5` | $2.00 | $10.00 | Half |
| `claude-haiku-5-5`, prompts up to 100K tokens | $0.10 | $0.50 | 1/40 |
| `claude-haiku-5-5`, prompts beyond 100K tokens † | $0.50 | $2.50 | 1/8 |

Set the model with `LISTER_MODEL` in `.env`. Haiku 5.5 may need code changes: † `lister/llm.py` requests server-side fallbacks on every
structured call, and the same reference says Haiku 5.5 has none for refusals. Photo ID on Opus 5.5 is a guess at $0.05–$0.20 per item.

## Cost of switching provider

Not just a setting:
- **Modest change:** photo ID, pasted sales and listing text all go through `structured()` in `lister/llm.py`.
- **Rebuild:** web search uses Claude-only tools (`websearch.py:100-109`).

## Recommendations

1. **Compare first.** Run the photos through Claude, Gemini Flash and Qwen3-VL 8B, then check every field by hand. That is a better
   test than published benchmarks.
2. **Photo ID.** Use a free model only if it gets name, number, grader, grade and cert right on every slab. Otherwise keep Claude.
3. **Base prices.** Use eBay active and TCGdex, plus PriceCharting if you sell enough TAG 10s or games to justify it.
4. **Sold prices.** Paste them in and let a model read them: Claude, or the local model if it tests well. This is the most reliable
   sold data available and matters most for expensive slabs.
5. **Web search.** Set `LISTER_WEB_SEARCH=false` until you have compared it with pasted sales on 5–10 cards. Before relying on it, add
   a check that each price appears on the page.

## Sources

| Source | How it was read |
|---|---|
| [Gemini pricing](https://aistudio.google.com/docs/pricing) | First part read directly, the rest through a summary |
| [Gemini rate limits](https://aistudio.google.com/docs/rate-limits) | Read in full |
| [OpenRouter free APIs](https://openrouter.ai/blog/tutorials/free-llm-apis-compared/) | Search summary only |
| [Roboflow local vision models](https://blog.roboflow.com/local-vision-language-models/) | Search summary only |
| [InsiderLLM vision guide](https://insiderllm.com/guides/vision-models-locally/) | Search summary only |
| [LLMCheck Mac vision guide](https://llmcheck.net/blog/best-local-vision-model-mac/) | Search summary only |
| [Apidog search APIs](https://apidog.com/blog/free-web-search-api/) | Search summary only |

Free tiers change often. Check current limits before relying on them.
