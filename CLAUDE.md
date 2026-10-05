# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

An `AGENTS.md` also exists in this repo for other coding agents; keep the two
in sync when architecture, commands, or CLI flags change.

## Project overview

**resume-matcher** is a single-module Python tool that scores how well a pool
of resumes matches scraped job descriptions. Instead of generating text, it
does a logit read on a Qwen3 model: the model is loaded once, kept resident in
memory, and each (resume, job) pair is scored by comparing the mean
log-probability of full option phrases (e.g. `["strong match", "possible
match", "no match"]`) after a chat-templated prompt. Output is a lean JSONL
stream of matches above a confidence threshold.

There is no packaging metadata (no `pyproject.toml`/`setup.py`/
`requirements.txt`) and no test suite or CI — this is intentional single-file
scaffolding (see Code style below), not an oversight to fix.

## Commands

```bash
# install (GPU)
pip install torch transformers bitsandbytes accelerate
# install (CPU) — bitsandbytes not needed
pip install torch transformers accelerate
# optional backends
pip install torchao            # for --int8 on CPU
pip install llama-cpp-python   # for the GGUF/llama.cpp backend

# static check (no model load)
python -m py_compile job_matcher.py
python -c "import job_matcher"   # cheap dependency sanity check

# run
python job_matcher.py --resume cv.md --jobs "jobs/*.md"
python job_matcher.py --resumes "pool/*.md" --jobs "jobs/**/*.txt" --out results.jsonl
python job_matcher.py --resumes "pool/*.md" --jobs "jobs/*.md" --min-strong 0.5
python job_matcher.py --resume cv.md --jobs "jobs/*.md" --mode embed

# benchmark: scores the full resumes/*.md x jobs/*.md sweep into results_<mode>.jsonl
# and checks the ranking proof (QA roles top, Delphi last) + verdict agreement
python benchmark.py run <mode>     # classify | criteria | category | rank | embed
python benchmark.py check <mode>   # re-check an existing results file
```

There is no automated test suite. If you change scoring logic, verify
end-to-end with a small real run (a couple of resume/job files) and inspect
the JSONL output — `Matcher()` downloads the model from Hugging Face on first
use, so full verification needs network access. CPU-only machines fall back
to a smaller model with generally less reliable scores than the GPU model.

## Architecture (`job_matcher.py`)

- Module constants `MODEL_ID` (`Qwen/Qwen3-4B-Instruct-2507`, GPU), `CPU_MODEL_ID`
  (`Qwen/Qwen3-1.7B`, CPU fallback) and `OPTIONS` define the default models and
  scoring buckets; `_default_model_id()` picks GPU vs CPU based on
  `torch.cuda.is_available()`. Options are scored as full phrases (mean
  log-prob per option, not first-token), so multi-token options are safe.
- `_BaseMatcher` holds shared scoring logic: `_build_prompt` applies the
  tokenizer's chat template with a per-mode `SYSTEM_PROMPT`; `score(resume,
  job)` softmaxes per-option mean log-probs from the backend-specific
  `_option_logprobs`. `score_criteria` (`--mode criteria`) reads each
  `CRITERIA` entry as a yes/no logit. `score_category` (`--mode category`) is
  a constrained yes/no/maybe read — single-token labels are deliberate,
  since multi-token labels like "mismatch" get inflated mean log-probs from
  their predictable tails (see README benchmarks). `strong_logprob` backs
  `--mode rank`, which softmaxes across jobs per resume instead of across
  options. `score_batch` loops `score` over pairs.
- `Matcher(_BaseMatcher)` — HuggingFace backend: 4-bit bnb quantization on
  CUDA, bfloat16 (or int8 weight-only via torchao with `--int8`) on CPU.
- `LlamaMatcher(_BaseMatcher)` — llama.cpp backend, selected automatically
  when `--model` points at a `.gguf` file. Tokenizes/evaluates via
  `llama_cpp.Llama` (`llm.reset(); llm.eval(tokens)`, reads `llm.scores`);
  still uses the HF tokenizer for chat-template formatting. This is the fast
  CPU path (~2x HF bf16 at a third of the memory).
- `Embedder` (used only by `--mode embed`; the logit-read matcher is not
  loaded in this mode) embeds documents with a bi-encoder
  (`EMBED_MODEL_ID`, default Qwen3-Embedding-0.6B) and scores pairs by cosine
  similarity. Pooling follows model family (last-token for Qwen3-Embedding,
  mean with an E5-style `passage: ` prefix otherwise). `_sections` splits
  documents over `SECTION_CHARS` (8000 chars) into paragraph-packed spans;
  `embed_document` averages renormalized section vectors. Section vectors are
  cached in SQLite via `EmbeddingCache` (`--embed-cache`, default
  `embeddings.sqlite`), keyed by (path, start, end, mtime_ns, model), so
  re-runs only embed what changed; stale mtimes are pruned on write.
- `_expand_patterns` expands glob patterns (or a `--jobs-file` manifest, one
  pattern per line) into a deduplicated, order-preserving `Path` list.
- `main()` parses args, reads all resumes into memory up front, picks the
  scoring path (`embed` → `Embedder`, a `.gguf` model path → `LlamaMatcher`,
  else `Matcher`), scores every (job, resume) pair, and writes JSONL records
  whose confidence passes `--min-strong` (default 0.3; ignored in rank mode).
  `--time-budget` (seconds, classify/criteria/category/rank only) checks
  elapsed wall-clock time before each job and stops gracefully once it's
  exceeded, leaving already-written records intact — useful for capping a
  run against a large job pool without reloading the model.

### Choosing a mode

Per the README's benchmark runs on the CPU fallback model (Qwen3-1.7B): only
`classify` and `embed` pass the ranking proof (QA roles ranked above the
off-target Delphi role) — `category` saturates to all-"yes", and `criteria`
saturates to all-"yes" per criterion. `embed` is also the cheapest to rerun
at scale (SQLite-cached, near-free after first pass) and is meant as a
coarse pre-filter before running a logit-read mode on the shortlist. These
failure modes are specific to the small CPU model; re-verify before trusting
category/criteria mode output from the 4B GPU model.

## Code style

- Plain, dependency-light Python (3.10+, uses `list[str]`/`str | None` style
  hints); stdlib plus the ML packages above only.
- Type hints on signatures; no comments except docstrings on the module,
  helpers, and public methods.
- Small helpers prefixed with `_`; errors/warnings go to stderr, results to
  stdout or `--out`.
- Keep changes minimal and consistent with the single-file structure — do not
  introduce packaging or framework scaffolding unless asked.

## Security considerations

- Resume/job files are read as plain text and passed straight into the model
  prompt — treat their contents as untrusted prompt content.
- Glob patterns come from CLI args or `--jobs-file`; the tool reads whatever
  local files those patterns match, so don't feed it attacker-controlled
  pattern lists.
- Output JSONL includes full probability distributions and file paths.
