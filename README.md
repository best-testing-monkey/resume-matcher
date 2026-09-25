# job_matcher

Match a pool of resumes against scraped job descriptions using a small local LLM.
Built on Qwen3 (4-bit quantized on GPU; on CPU either bfloat16 via
HuggingFace transformers or any GGUF quant via llama.cpp) with a
SemIf-style logit read — no text generation. Prompts use the model's chat
template with a strict-recruiter system prompt. Five scoring modes
(`--mode`): `classify` (default) compares the mean log-probability of the
full phrases "strong match" / "possible match" / "no match"; `criteria`
scores role, skills, seniority and practical requirements as separate yes/no
reads; `category` is a constrained yes/no/maybe verdict with a confidence
factor; `rank` softmaxes the strong-match log-prob across jobs per resume
(which job fits this CV best); `embed` skips the generative model entirely
and takes the cosine similarity between bi-encoder embedding vectors of the
two documents. `benchmark.py` verifies ranking and verdict
agreement against labeled ground truth.

## Why this exists

Feeding a full LLM to score "does this resume fit this job?" is slow and expensive.
This module loads the model once, keeps it resident in memory, and scores
hundreds of pairs in one run. Output is a lean JSONL of confident matches only.

## Requirements

- Python 3.10+
- NVIDIA GPU with ~5 GB free VRAM (6 GB card, realistic budget)
- CPU-only machines also work. Three paths, fastest last:
  - HuggingFace bf16 (default): weights are memory-mapped; even the 4B model
    runs, just slowly (~3-11 min/pair). int8 weight-only via torchao is
    available with `--int8` but brings no speed gain on ARM (int4 is not
    usable on aarch64 — it requires the `mslk` package, which has no ARM
    wheel).
  - llama.cpp: pass a GGUF file with `--model path/to/model.gguf` (requires
    `llama-cpp-python`). Roughly 2x faster than HF bf16 at a fraction of the
    memory, with quant levels from Q2_K up to Q8_0 to trade speed for
    precision. See the GGUF section below.
- Dependencies:

```bash
pip install torch transformers bitsandbytes accelerate
# bitsandbytes is only needed on GPU; on CPU: pip install torch transformers accelerate
# optional: torchao (for --int8), llama-cpp-python (for the GGUF backend)
```

## Example results

Real run: one CV (senior test automation engineer) in 6 length variants plus a
compact version, scored against 4 scraped freelance job listings. Cells show
P(strong match) / P(no match); Qwen3-1.7B on CPU, chat-templated prompt with
full-phrase scoring, `--min-strong 0.0`:

| Resume | TAE (overheid) | Java dev (medior) | Tester (RVO) | Delphi specialist |
|---|---|---|---|---|
| cv_tim_jansen_compact.md | 0.51/0.15 | 0.42/0.11 | 0.51/0.15 | 0.41/0.12 |
| cv_1000.md | 0.55/0.18 | 0.55/0.12 | 0.63/0.11 | 0.50/0.11 |
| cv_750.md | 0.50/0.11 | 0.52/0.12 | 0.52/0.12 | 0.58/0.11 |
| cv_500.md | 0.44/0.11 | 0.44/0.11 | 0.48/0.14 | 0.51/0.10 |
| cv_250.md | 0.44/0.11 | 0.50/0.11 | 0.36/0.17 | 0.41/0.13 |
| cv_150.md | 0.50/0.11 | 0.47/0.11 | 0.38/0.14 | 0.50/0.16 |
| cv_100.md | 0.40/0.09 | 0.42/0.09 | 0.39/0.16 | 0.44/0.11 |

Runtime on a 6-core aarch64 CPU (11 GB RAM, no GPU): 74 min for 28 pairs
(~2.6 min/pair; full-phrase scoring costs one forward pass per option).
Compared to first-token scoring, probabilities are far less inflated (nothing
saturates near 1.0) but the 1.7B model still ranks weak fits too close to
good ones — the off-target Delphi role stays within ~0.1 of the QA roles.
Treat scores as rough rankings; the GPU model (Qwen3-4B-Instruct-2507)
discriminates noticeably better.

### Criteria mode (`--mode criteria`)

Benchmark: 2 CVs (longest and shortest) x 2 jobs (on-target tester role,
off-target Delphi role), 34 min for 4 pairs (~8.6 min/pair; one forward pass
per criterion). Result: P(yes) saturates at 1.000 for every criterion on every
pair — even the 100-token CV against the Delphi role gets "yes" on role fit,
skills, seniority and practical requirements. The 1.7B model is too sycophantic
for binary yes/no questions, so criteria mode is not usable with the CPU
fallback model. It may still be worthwhile with the 4B GPU model, where the
per-criterion breakdown doubles as an explanation of the verdict.

### Rank mode (`--mode rank`)

Full sweep (28 pairs, ~37 min; one forward pass per pair, then softmax across
jobs per resume). Ranking proof (QA roles top, Delphi last, long CVs):
**PASS for cv_1000** (TAE 0.290 > RVO 0.256 > Java 0.256 > Delphi 0.199) but
**FAIL for the compact CV** (Java ties TAE at 0.304, RVO drops to 0.209).
Cheapest mode and the only one whose scores are directly comparable across
jobs, but the small log-prob spread produces near-ties.

### Category mode (`--mode category`)

Uses single-token labels yes/no/maybe — multi-token labels are unusable here:
"mismatch" tokenizes with a highly predictable tail, which inflates its mean
log-probability so much that *every* pair scored P(mismatch) = 1.0 regardless
of prompt (6 prompt variants tried). With yes/no/maybe the same saturation
flips direction: full sweep (28 pairs, ~2h10m) returned "yes" for every pair,
including both short CVs against the Delphi role. Verdict agreement vs ground
truth: 14/28 — exactly the all-yes baseline. Not usable with the CPU fallback
model.

### llama.cpp (GGUF) backend

Pass any GGUF file with `--model` to switch from HuggingFace transformers to
llama.cpp — the fast CPU path. The HF tokenizer is used only for chat-template
formatting; all inference runs through llama.cpp (`n_ctx=8192`, all cores).

```bash
pip install llama-cpp-python   # builds from source on aarch64; on weak
                               # machines build gently: nice -n 19 env \
                               # CMAKE_BUILD_PARALLEL_LEVEL=2 pip install llama-cpp-python
HF_HUB_DISABLE_XET=1 huggingface-cli download unsloth/Qwen3-4B-Instruct-2507-GGUF \
    Qwen3-4B-Instruct-2507-Q4_K_M.gguf
python job_matcher.py --resume cv.md --jobs "jobs/*.md" \
    --model ~/.cache/huggingface/hub/models--unsloth--Qwen3-4B-Instruct-2507-GGUF/snapshots/*/Qwen3-4B-Instruct-2507-Q4_K_M.gguf
```

(`HF_HUB_DISABLE_XET=1` works around xet CDN errors on flaky networks.) The
unsloth repo offers quants from Q2_K up to Q8_0 — lower quants are faster and
smaller, Q8_0 is near-lossless. Measured on the 6-core aarch64 CPU, Qwen3-4B,
classify mode:

| Backend / quant | cv_1000 x Delphi | cv_100 x RVO tester | Resident RAM |
|---|---|---|---|
| HF bf16 | 10m49s, no match 1.0 | 3m00s, strong 1.0 | ~8 GB (mmap) |
| GGUF Q4_K_M | 5m35s, no match 1.0 | 2m40s, strong 1.0 | ~2.4 GB |
| GGUF Q8_0 | 4m36s, no match 1.0 | — | ~4.3 GB |

Verdicts are identical across backends on these probe pairs — the 4B
discriminates decisively even at Q4_K_M, at ~2x the speed and under a third
of the memory of HF bf16. Note that Q8_0 is *faster* than Q4_K_M here:
K-quant decompression costs more CPU per weight than Q8_0's simpler layout,
so on this device the quant ladder trades memory, not speed.

### Embed mode (`--mode embed`)

No generative model at all: each document is embedded once with a bi-encoder
(default `Qwen/Qwen3-Embedding-0.6B`, override with `--embed-model`), and a
pair's score is the cosine similarity between the two vectors. Documents
longer than 8000 characters are embedded in paragraph-packed sections; every
section vector is cached in SQLite (`--embed-cache`, default
`embeddings.sqlite`), keyed by file name, section start+end character
offsets, last-modified time and model. Re-runs only embed what changed, so
this mode is nearly free after the first pass and scales to large resume
pools: embed everything once, then matching is a dot product.

Benchmark (Qwen3-Embedding-0.6B, cosine similarity, 6-core aarch64 CPU):

| Resume | TAE (overheid) | Java dev (medior) | Tester (RVO) | Delphi specialist |
|---|---|---|---|---|
| cv_tim_jansen_compact.md | 0.735 | 0.488 | 0.649 | 0.355 |
| cv_1000.md | 0.732 | 0.488 | 0.650 | 0.365 |
| cv_750.md | 0.738 | 0.532 | 0.681 | 0.390 |
| cv_500.md | 0.734 | 0.506 | 0.672 | 0.385 |
| cv_250.md | 0.690 | 0.478 | 0.651 | 0.349 |
| cv_150.md | 0.712 | 0.460 | 0.646 | 0.355 |
| cv_100.md | 0.703 | 0.505 | 0.663 | 0.386 |

Every CV variant ranks TAE > RVO > Java > Delphi, so the ranking proof
**passes for both long CVs** — and with far wider margins than any 1.7B
logit-read mode (QA roles ~0.65-0.74 vs Delphi ~0.35-0.39, where classify
mode kept everything within ~0.1). Scores are stable across CV lengths —
even the 100-token CV ranks correctly, though that is topical agreement
more than requirement checking.

Runtime: a few seconds of compute for the 11 documents on first pass
(plus a one-time ~1.2 GB model download); a warm-cache rerun of all 28
pairs takes ~70 s on this device, almost all of it model load, and
reproduces the scores bit-for-bit.

Use it as a coarse pre-filter: shortlist with embeddings, then run the 4B
logit read on the shortlist for an actual verdict. Cosine similarity is a
ranking signal, not a calibrated probability — in a homogeneous job pool all
scores land in a narrow band.

### Benchmark verdict

`python benchmark.py check <mode>` verifies the ranking proof (QA roles top,
Delphi last, for cv_1000 and cv_tim_jansen_compact). On Qwen3-1.7B the proof
**passes only in classify mode** (both long CVs; see table above) — and in
**embed mode**, where Qwen3-Embedding-0.6B passes with wide margins. The
absolute probabilities remain weakly calibrated — usable as an indicator,
not a decision.

