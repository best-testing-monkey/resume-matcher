# AGENTS.md

## Project overview

**resume-matcher** is a single-module Python tool that scores how well a pool of
resumes matches scraped job descriptions. Instead of generating text, it uses a
SemIf-style logit read on a Qwen3 model: the model is loaded once, kept resident
in memory, and each
(resume, job) pair is scored by comparing the mean log-probability of the full
option phrases `["strong match", "possible match", "no match"]` after a
chat-templated prompt. Output is a lean JSONL stream containing only matches
above a confidence threshold.

The project files:

- `job_matcher.py` — the whole implementation (library + CLI)
- `benchmark.py` — runs scoring sweeps per mode and checks ranking/verdict
  agreement against labeled ground truth
- `README.md` — usage and requirements documentation

There is no packaging metadata (no `pyproject.toml`, `setup.py`, or
`requirements.txt`), no test suite, no CI configuration, and it is not a git
repository.

## Technology stack and runtime architecture

- **Language:** Python 3.10+ (uses modern type-hint syntax such as
  `list[str]`, `dict[str, float]`, `str | None`).
- **Key dependencies** (installed manually with pip, see README):
  `torch`, `transformers`, `bitsandbytes`, `accelerate`; optional: `torchao`
  (CPU `--int8`), `llama-cpp-python` (GGUF backend).
- **Model (GPU):** `Qwen/Qwen3-4B-Instruct-2507`, loaded with
  `BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16,
  bnb_4bit_use_double_quant=True)` and `device_map="auto"`.
- **Model (CPU fallback):** `Qwen/Qwen3-1.7B` in bfloat16 with
  `device_map="cpu"`, selected automatically when `torch.cuda.is_available()`
  is false (`_default_model_id()`); `--model` overrides either default.
  bitsandbytes is not required on the CPU path. CPU loads bf16 by default;
  `--int8` (requires torchao) loads int8 weight-only
  (`TorchAoConfig(Int8WeightOnlyConfig())`) instead — scores shift slightly
  (int8 noise) and there is no speed gain on generic ARM kernels; int4 is
  unusable on aarch64 (requires `mslk`, no ARM wheel). Even the 4B model runs
  on CPU via memory-mapped weights (~3-11 min/pair depending on prompt
  length).
- **Model (llama.cpp/GGUF):** passing a `.gguf` path to `--model` selects
  `LlamaMatcher`, which runs inference through llama.cpp (`n_ctx=8192`,
  `logits_all=True`, `n_threads=os.cpu_count()`) while using the HF tokenizer
  of `MODEL_ID` only for chat-template formatting. This is the fast CPU path:
  ~2x faster than HF bf16 at a third of the memory, with identical verdicts
  on probe pairs at Q4_K_M. GGUFs come from
  `unsloth/Qwen3-4B-Instruct-2507-GGUF` (quants Q2_K to Q8_0; download with
  `HF_HUB_DISABLE_XET=1` on flaky networks).
- **Hardware requirement:** NVIDIA GPU with roughly 5 GB free VRAM for the
  full model; CPU-only works with the smaller fallback model but scores
  slowly.

### Code organization (`job_matcher.py`)

- Module constants `MODEL_ID`, `CPU_MODEL_ID` and `OPTIONS` define the default
  models and the three scoring buckets; `_default_model_id()` picks `MODEL_ID`
  on CUDA and `CPU_MODEL_ID` otherwise. Options are scored as full phrases
  (mean log-prob per option), so multi-token options are safe.
- `_BaseMatcher` holds the shared scoring logic: `_build_prompt` applies the
  tokenizer's chat template with `SYSTEM_PROMPT` (overridable per mode);
  `score(resume, job)` softmaxes the per-option mean log-probs from the
  backend-specific `_option_logprobs` and returns `{option: probability}`.
  `score_criteria` answers each `CRITERIA` entry as a yes/no logit read
  (`--mode criteria`, also reachable via the `--criteria` alias).
  `score_category` is a constrained yes/no/maybe read with a confidence
  factor (`--mode category`); single-token labels are deliberate —
  multi-token labels like "mismatch" get inflated mean log-probs from their
  predictable tails. `strong_logprob` returns the raw mean log-prob of
  "strong match"; `--mode rank` collects it for all pairs and softmaxes
  across jobs per resume (records get `strong_logprob`,
  `probs: {"best fit": p}`, and `top: "best fit"` on the argmax job, else
  null). `score_batch` is a convenience loop over `score`.
- `Matcher(_BaseMatcher)` is the HuggingFace backend: on CUDA it loads with
  bnb 4-bit quantization, on CPU in bfloat16 (or int8 weight-only via torchao
  with `int8=True`). `__del__` frees the model and calls
  `torch.cuda.empty_cache()` (CUDA only).
- `LlamaMatcher(_BaseMatcher)` is the llama.cpp backend: constructed with a
  GGUF file path, it tokenizes/evaluates via `llama_cpp.Llama`
  (`llm.reset(); llm.eval(tokens)`, reading `llm.scores`) and uses the HF
  tokenizer only for chat-template formatting.
- `Embedder` (used by `--mode embed`; the logit-read matcher is not loaded
  in this mode) embeds documents with a bi-encoder (`EMBED_MODEL_ID`
  = Qwen3-Embedding-0.6B, `--embed-model` overrides) and scores pairs by
  cosine similarity. Pooling follows the model family: last-token for
  Qwen3-Embedding, mean with a `passage: ` prefix for E5. `_sections`
  splits documents longer than `SECTION_CHARS` (8000) into paragraph-packed
  character spans; `embed_document` averages the (renormalized) section
  vectors. Section vectors are stored by `EmbeddingCache`, a SQLite cache
  (`--embed-cache`, default `embeddings.sqlite`) keyed by (path, start,
  end, mtime_ns, model) so re-runs only embed what changed and future
  smarter sectioning reuses the same key scheme; stale mtimes are pruned
  on write.
- `_expand_patterns(patterns, source_file)` expands glob patterns (or a
  manifest file with one pattern per line, via `--jobs-file`) into a
  deduplicated, order-preserving `Path` list, warning on empty matches.
- `main()` is the CLI entry point: parses args, expands resume/job patterns,
  reads all resumes into memory up front, picks the scoring path (`embed`
  mode → `Embedder`, a `.gguf` model path → `LlamaMatcher`, otherwise
  `Matcher`), then scores every (job,
  resume) pair and writes JSONL records whose confidence passes
  `--min-strong` (default 0.3). Each record has `resume_file`, `job_file`,
  `probs`, and `top`; with `--criteria` it also has `criteria`
  (per-criterion P(yes)).

## Build and test commands

There is no build step and no test suite — nothing is packaged. Verification is
manual:

```bash
pip install torch transformers bitsandbytes accelerate

# smoke-test the scoring path (downloads the model on first run)
python job_matcher.py --resume cv.md --jobs "jobs/*.md"
python job_matcher.py --resumes "pool/*.md" --jobs "jobs/**/*.txt" --out results.jsonl
python job_matcher.py --resumes "pool/*.md" --jobs "jobs/*.md" --min-strong 0.5
```

For quick static checks, `python -m py_compile job_matcher.py` confirms the file
parses. Importing the module does not load the model, so
`python -c "import job_matcher"` is a cheap sanity check that dependencies are
installed.

## Usage

Library:

```python
from job_matcher import Matcher
m = Matcher()
result = m.score(resume_text, job_text)  # {"strong match": ..., "possible match": ..., "no match": ...}
```

CLI flags: `--resume` (single file) or `--resumes` (glob patterns); `--jobs`
(glob patterns) or `--jobs-file` (manifest, one pattern per line); `--out`
(output JSONL file, default stdout); `--model` (override model ID; a path
ending in `.gguf` selects the llama.cpp backend); `--mode
{classify,criteria,category,rank,embed}` (scoring mode, default classify;
`embed` uses the bi-encoder, not the logit-read model); `--embed-model`
(embedding model for embed mode, default Qwen3-Embedding-0.6B);
`--embed-cache` (SQLite cache for section embeddings, default
`embeddings.sqlite`);
`--criteria` (alias for `--mode criteria`); `--int8` (CPU HF backend only:
int8 weight-only via torchao instead of bf16); `--min-strong` (default 0.3;
in category mode it thresholds the verdict's confidence; ignored in rank
mode).

Benchmark: `python benchmark.py run <mode>` scores the full
`resumes/*.md` x `jobs/*.md` sweep into `results_<mode>.jsonl` and checks the
ranking proof (QA roles top, Delphi last, for the two long CVs) and, for
category mode, verdict agreement vs ground truth. `python benchmark.py check
<mode>` re-checks an existing results file.

## Code style guidelines

- Plain, dependency-light Python; stdlib plus the ML packages listed above
  only (torchao and llama-cpp-python are optional and imported lazily).
- Type hints on signatures; no comments except docstrings on the module,
  helpers, and public methods.
- Small helpers prefixed with `_`; errors and warnings go to stderr, results to
  stdout/`--out`.
- Keep changes minimal and consistent with the single-file structure — do not
  introduce packaging or framework scaffolding without being asked.

## Testing instructions

No automated tests exist. If you add or change scoring logic, verify it
end-to-end with a real small run (a couple of resume/job files) and
inspect the JSONL output. Note that `Matcher()` downloads the model from
Hugging Face on first use, so full verification requires network access;
on CPU-only machines the smaller fallback model is used, so expect
different (generally less reliable) scores than the GPU model.

## Security considerations

- Input files (resumes, job descriptions) are read with
  `p.read_text(encoding="utf-8")` and passed straight into the model prompt —
  treat them as untrusted prompt content.
- Glob patterns come from CLI args or `--jobs-file`; the tool reads arbitrary
  local files those patterns match, so do not feed it attacker-controlled
  pattern lists.
- Output records include the full probability distribution and file paths;
  be mindful of writing them to shared locations.
- `torch.cuda.empty_cache()` runs in `__del__` on CUDA machines; avoid adding
  credential or secret handling to this module.
