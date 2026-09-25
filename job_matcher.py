# job_matcher.py
"""Job-resume matching via SemIf-style logit reading on Qwen3.

Prompts are built with the tokenizer's chat template and a system prompt.
Scoring compares the full option phrases (mean log-probability per option,
softmaxed), not just their first tokens.

On CUDA GPUs the default model is Qwen3-4B-Instruct-2507 (bnb 4-bit).
On CPU-only machines it falls back to Qwen3-1.7B in bfloat16.

Library usage:
    from job_matcher import Matcher
    m = Matcher()
    result = m.score(resume_text, job_text)

CLI usage:
    python job_matcher.py --resume cv.md --jobs "jobs/*.md"
    python job_matcher.py --resumes "pool/*.md" --jobs "jobs/**/*.txt" --out results.jsonl
    python job_matcher.py --resumes "pool/*.md" --jobs "jobs/*.md" --min-strong 0.5
    python job_matcher.py --resumes "pool/*.md" --jobs "jobs/*.md" --mode rank

Modes: classify (default, 3-way full-phrase read), criteria (per-criterion
yes/no), category (constrained yes/no/maybe verdict with confidence),
rank (softmax across jobs per resume — which job fits this CV best),
embed (bi-encoder cosine similarity, cached per file section in SQLite).
"""

import argparse
import glob
import json
import os
import sqlite3
import sys
from array import array
from importlib.util import find_spec
from pathlib import Path

import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TorchAoConfig,
)

MODEL_ID = "Qwen/Qwen3-4B-Instruct-2507"
CPU_MODEL_ID = "Qwen/Qwen3-1.7B"
EMBED_MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"
SECTION_CHARS = 8000  # embed documents longer than this in paragraph-packed spans
OPTIONS = ["strong match", "possible match", "no match"]
SYSTEM_PROMPT = (
    "You are a strict technical recruiter. Judge how well the candidate "
    "matches the job based only on evidence in the resume. Answer with "
    "exactly one of: strong match, possible match, no match."
)
CRITERIA = [
    "the candidate's role and experience fit the job's role",
    "the candidate has the job's must-have skills and tools",
    "the candidate's seniority matches the job's level",
    "the candidate meets practical requirements (language, location, hours)",
]
CATEGORIES = ["yes", "no", "maybe"]
CATEGORY_SYSTEM_PROMPT = (
    "You are a strict technical recruiter. Judge how well the candidate "
    "matches the job based only on evidence in the resume. Answer with "
    "exactly one word: yes, no, or maybe."
)
CATEGORY_QUESTION = "Does this candidate match this job? Answer yes, no, or maybe."


def _default_model_id() -> str:
    return MODEL_ID if torch.cuda.is_available() else CPU_MODEL_ID


class _BaseMatcher:
    """Shared prompt building and scoring. Subclasses provide _option_logprobs."""

    options: list[str]

    def _build_prompt(
        self,
        resume: str,
        job: str,
        question: str | None = None,
        system: str | None = None,
    ) -> str:
        q = question or "How well does this candidate match this job?"
        messages = [
            {"role": "system", "content": system or SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Job description:\n{job}\n\n"
                    f"Candidate resume:\n{resume}\n\n"
                    f"{q}"
                ),
            },
        ]
        return self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )

    def score(self, resume: str, job: str) -> dict[str, float]:
        """Score one (resume, job) pair. Returns {option: probability}."""
        prompt = self._build_prompt(resume, job)
        logps = torch.tensor(self._option_logprobs(prompt, self.options))
        probs = torch.softmax(logps, dim=0)
        return dict(zip(self.options, probs.tolist()))

    def score_category(self, resume: str, job: str) -> dict[str, float]:
        """Constrained single-category read: yes / no / maybe.

        Single-token labels avoid the mean-logprob inflation that multi-token
        labels (e.g. 'mismatch') get from their highly predictable tails.
        The category with the highest probability is the verdict; its
        probability is the confidence factor.
        """
        prompt = self._build_prompt(
            resume, job, question=CATEGORY_QUESTION, system=CATEGORY_SYSTEM_PROMPT
        )
        logps = torch.tensor(self._option_logprobs(prompt, CATEGORIES))
        probs = torch.softmax(logps, dim=0)
        return dict(zip(CATEGORIES, probs.tolist()))

    def strong_logprob(self, resume: str, job: str) -> float:
        """Mean log-probability of 'strong match'; raw input for rank mode."""
        prompt = self._build_prompt(resume, job)
        return self._option_logprobs(prompt, ["strong match"])[0]

    def score_criteria(self, resume: str, job: str) -> dict:
        """Score each hard-requirement criterion yes/no, combine into a verdict.

        P(strong) is the joint probability that all criteria hold (treated as
        independent), P(no match) that all fail; the remainder is possible.
        Returns {"criteria": {criterion: P(yes)}, "probs": {option: probability}}.
        """
        per_criterion: dict[str, float] = {}
        p_all_yes = 1.0
        p_all_no = 1.0
        for criterion in CRITERIA:
            prompt = self._build_prompt(
                resume, job, f"Is it true that {criterion}? Answer yes or no."
            )
            logps = torch.tensor(self._option_logprobs(prompt, ["yes", "no"]))
            p_yes, p_no = torch.softmax(logps, dim=0).tolist()
            per_criterion[criterion] = p_yes
            p_all_yes *= p_yes
            p_all_no *= p_no
        probs = {
            "strong match": p_all_yes,
            "possible match": max(0.0, 1.0 - p_all_yes - p_all_no),
            "no match": p_all_no,
        }
        return {"criteria": per_criterion, "probs": probs}

    def score_batch(self, pairs: list[tuple[str, str]]) -> list[dict[str, float]]:
        """Score multiple pairs. Model stays loaded throughout."""
        return [self.score(r, j) for r, j in pairs]


class Matcher(_BaseMatcher):
    """HuggingFace/transformers backend (CUDA 4-bit bnb, CPU bf16/int8)."""

    def __init__(
        self,
        model_id: str = MODEL_ID,
        options: list[str] = OPTIONS,
        int8: bool = False,
    ):
        self.options = options

        self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        if torch.cuda.is_available():
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_use_double_quant=True,
            )
            self.model = AutoModelForCausalLM.from_pretrained(
                model_id,
                quantization_config=bnb_config,
                device_map="auto",
            )
        else:
            kwargs = {"dtype": torch.bfloat16, "device_map": "cpu"}
            if int8:
                if find_spec("torchao"):
                    from torchao.quantization import Int8WeightOnlyConfig

                    kwargs["quantization_config"] = TorchAoConfig(
                        Int8WeightOnlyConfig()
                    )
                else:
                    print(
                        "warning: --int8 given but torchao not installed; "
                        "loading unquantized bf16",
                        file=sys.stderr,
                    )
            self.model = AutoModelForCausalLM.from_pretrained(model_id, **kwargs)
        self.model.eval()

    @torch.no_grad()
    def _option_logprobs(self, prompt: str, options: list[str]) -> list[float]:
        """Mean log-probability of each full option phrase given the prompt."""
        prompt_ids = self.tokenizer(prompt, add_special_tokens=False)["input_ids"]
        results = []
        for o in options:
            option_ids = self.tokenizer.encode(o, add_special_tokens=False)
            ids = torch.tensor(
                [prompt_ids + option_ids], device=self.model.device
            )
            logits = self.model(ids).logits[0]
            start = len(prompt_ids) - 1
            option_logits = logits[start : start + len(option_ids)]
            logps = torch.log_softmax(option_logits, dim=-1)
            token_logps = logps[range(len(option_ids)), option_ids]
            results.append(token_logps.mean().item())
        return results

    def __del__(self):
        if hasattr(self, "model"):
            del self.model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


class LlamaMatcher(_BaseMatcher):
    """llama.cpp backend for GGUF models; fast on CPU, any quant level.

    The HF tokenizer is only used for chat-template formatting and option
    tokenization; all inference runs through llama.cpp.
    """

    def __init__(
        self,
        model_path: str,
        options: list[str] = OPTIONS,
        tokenizer_id: str = MODEL_ID,
        n_ctx: int = 8192,
    ):
        from llama_cpp import Llama

        self.options = options
        self.tokenizer = AutoTokenizer.from_pretrained(tokenizer_id)
        self.llm = Llama(
            model_path=model_path,
            n_ctx=n_ctx,
            logits_all=True,
            n_threads=os.cpu_count() or 4,
            verbose=False,
        )

    def _option_logprobs(self, prompt: str, options: list[str]) -> list[float]:
        """Mean log-probability of each full option phrase given the prompt."""
        import numpy as np

        prompt_tokens = self.llm.tokenize(prompt.encode("utf-8"), add_bos=True)
        results = []
        for o in options:
            option_tokens = self.llm.tokenize(o.encode("utf-8"), add_bos=False)
            self.llm.reset()
            self.llm.eval(prompt_tokens + option_tokens)
            base = len(prompt_tokens) - 1
            logps = []
            for i, t in enumerate(option_tokens):
                row = np.asarray(self.llm.scores[base + i], dtype=np.float64)
                logps.append(
                    row[t] - row.max() - np.log(np.exp(row - row.max()).sum())
                )
            results.append(sum(logps) / len(logps))
        return results


class EmbeddingCache:
    """SQLite cache of section embeddings.

    Keyed by (path, start, end, mtime, model): file name + last-modified
    time capture which content it is, start/end mark the character span of
    the section within the file, and model because vectors are only
    comparable within one embedding model. Rows for older mtimes of the same
    path are pruned on write.
    """

    def __init__(self, db_path: str):
        self.db = sqlite3.connect(db_path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS sections ("
            "path TEXT, start INT, end INT, mtime INT, model TEXT, vector BLOB, "
            "PRIMARY KEY (path, start, end, mtime, model))"
        )

    def get(
        self, path: str, start: int, end: int, mtime: int, model: str
    ) -> list[float] | None:
        row = self.db.execute(
            "SELECT vector FROM sections WHERE path=? AND start=? AND end=? "
            "AND mtime=? AND model=?",
            (path, start, end, mtime, model),
        ).fetchone()
        if row is None:
            return None
        vec = array("f")
        vec.frombytes(row[0])
        return list(vec)

    def put(
        self,
        path: str,
        start: int,
        end: int,
        mtime: int,
        model: str,
        vector: list[float],
    ) -> None:
        self.db.execute(
            "DELETE FROM sections WHERE path=? AND model=? AND mtime<>?",
            (path, model, mtime),
        )
        self.db.execute(
            "INSERT OR REPLACE INTO sections VALUES (?,?,?,?,?,?)",
            (path, start, end, mtime, model, array("f", vector).tobytes()),
        )
        self.db.commit()


def _sections(text: str, max_chars: int = SECTION_CHARS) -> list[tuple[int, int]]:
    """Character spans to embed: one span for short documents, paragraph-
    packed spans for long ones. Character offsets (not tokens) keep cache
    keys stable across tokenizer changes."""
    if len(text) <= max_chars:
        return [(0, len(text))]
    spans = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            split = text.rfind("\n\n", start, end)
            if split > start:
                end = split
        spans.append((start, end))
        start = end
        while start < len(text) and text[start] == "\n":
            start += 1
    return spans


class Embedder:
    """Bi-encoder embeddings: one vector per document, cosine between them.

    Section vectors are cached in SQLite keyed by (path, start, end, mtime),
    so re-runs only embed what changed. Pooling follows the model family:
    last-token for Qwen3-Embedding, mean with a 'passage: ' prefix for E5.
    """

    def __init__(
        self, model_id: str = EMBED_MODEL_ID, cache_path: str = "embeddings.sqlite"
    ):
        from transformers import AutoModel

        self.model_id = model_id
        self.is_e5 = "e5" in model_id.lower()
        self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        self.model = AutoModel.from_pretrained(
            model_id,
            dtype=torch.bfloat16,
            device_map="cuda" if torch.cuda.is_available() else "cpu",
        )
        self.model.eval()
        self.cache = EmbeddingCache(cache_path)

    @torch.no_grad()
    def _embed_text(self, text: str) -> torch.Tensor:
        """Normalized embedding vector for one text span."""
        ids = self.tokenizer(
            text, return_tensors="pt", truncation=True, max_length=8192
        ).to(self.model.device)
        hidden = self.model(**ids).last_hidden_state[0]
        vec = hidden.mean(0) if self.is_e5 else hidden[-1]
        return torch.nn.functional.normalize(vec.float(), dim=0)

    def embed_document(self, path: Path) -> torch.Tensor:
        """Mean of the document's (cached) section vectors, renormalized."""
        mtime = path.stat().st_mtime_ns
        text = path.read_text(encoding="utf-8")
        vecs = []
        for start, end in _sections(text):
            cached = self.cache.get(str(path), start, end, mtime, self.model_id)
            if cached is None:
                span = text[start:end]
                if self.is_e5:
                    span = "passage: " + span
                vec = self._embed_text(span)
                self.cache.put(
                    str(path), start, end, mtime, self.model_id, vec.tolist()
                )
            else:
                vec = torch.tensor(cached)
            vecs.append(vec)
        return torch.nn.functional.normalize(torch.stack(vecs).mean(0), dim=0)

    def similarity(self, resume_path: Path, job_path: Path) -> float:
        """Cosine similarity between two documents' embedding vectors."""
        return float(self.embed_document(resume_path) @ self.embed_document(job_path))


def _expand_patterns(patterns: list[str], source_file: str | None) -> list[Path]:
    """Expand glob patterns / manifest file into a concrete, deduplicated path list."""
    paths: list[Path] = []

    if source_file:
        with open(source_file) as f:
            patterns = [line.strip() for line in f if line.strip()]

    for pat in patterns:
        matches = glob.glob(pat, recursive=True)
        if not matches:
            print(f"warning: pattern matched nothing: {pat}", file=sys.stderr)
        paths.extend(Path(m) for m in matches)

    seen = set()
    unique = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def main():
    parser = argparse.ArgumentParser(
        description="Score resume-to-job matches. Model loads once, scores all pairs, exits."
    )
    parser.add_argument("--resume", help="Single resume file (markdown/text)")
    parser.add_argument("--resumes", nargs="+", help="Glob pattern(s) for resume files")
    parser.add_argument("--jobs", nargs="+", help="Glob pattern(s) for job files")
    parser.add_argument("--jobs-file", help="Text file with one glob pattern per line")
    parser.add_argument("--out", help="Output JSONL file (default: stdout)")
    parser.add_argument(
        "--model",
        default=None,
        help=f"Override model ID (default: {MODEL_ID} on CUDA, {CPU_MODEL_ID} "
        "on CPU); a path to a .gguf file selects the llama.cpp backend",
    )
    parser.add_argument(
        "--mode",
        choices=["classify", "criteria", "category", "rank", "embed"],
        default="classify",
        help="Scoring mode: classify (3-way full-phrase read, default), "
        "criteria (per-criterion yes/no), category (constrained "
        "yes/no/maybe verdict with confidence), rank (relative "
        "softmax across jobs per resume), embed (bi-encoder cosine "
        "similarity, cached per section in SQLite)",
    )
    parser.add_argument(
        "--criteria",
        action="store_true",
        help="Alias for --mode criteria",
    )
    parser.add_argument(
        "--embed-model",
        default=EMBED_MODEL_ID,
        help=f"Embedding model for --mode embed (default: {EMBED_MODEL_ID})",
    )
    parser.add_argument(
        "--embed-cache",
        default="embeddings.sqlite",
        help="SQLite cache file for section embeddings "
        "(default: embeddings.sqlite)",
    )
    parser.add_argument(
        "--int8",
        action="store_true",
        help="CPU only: load int8 weight-only via torchao instead of bf16",
    )
    parser.add_argument(
        "--min-strong",
        type=float,
        default=0.3,
        help="Minimum P(strong match) to write a record (default: 0.3); "
        "in category mode, minimum confidence of the verdict; "
        "ignored in rank mode",
    )
    args = parser.parse_args()

    mode = "criteria" if args.criteria else args.mode

    if not args.resume and not args.resumes:
        parser.error("provide --resume or --resumes")
    if not args.jobs and not args.jobs_file:
        parser.error("provide --jobs or --jobs-file")

    if args.resume:
        resume_paths = [Path(args.resume)]
    else:
        resume_paths = _expand_patterns(args.resumes, None)

    job_paths = _expand_patterns(args.jobs or [], args.jobs_file)

    if not resume_paths:
        print("no resume files found", file=sys.stderr)
        sys.exit(1)
    if not job_paths:
        print("no job files found", file=sys.stderr)
        sys.exit(1)

    resumes = {str(p): p.read_text(encoding="utf-8") for p in resume_paths}

    out_f = open(args.out, "w", encoding="utf-8") if args.out else sys.stdout
    try:
        if mode == "embed":
            embedder = Embedder(args.embed_model, args.embed_cache)
            job_vecs = {str(jp): embedder.embed_document(jp) for jp in job_paths}
            for resume_path in resumes:
                rvec = embedder.embed_document(Path(resume_path))
                for job_path, jvec in job_vecs.items():
                    sim = float(rvec @ jvec)
                    if sim < args.min_strong:
                        continue
                    record = {
                        "resume_file": resume_path,
                        "job_file": job_path,
                        "probs": {"similarity": sim},
                        "top": "similarity",
                    }
                    out_f.write(json.dumps(record) + "\n")
                    out_f.flush()
            return

        model_arg = args.model or _default_model_id()
        if model_arg.endswith(".gguf"):
            matcher = LlamaMatcher(model_arg)
        else:
            matcher = Matcher(model_id=model_arg, int8=args.int8)

        if mode == "rank":
            logps = {}
            for job_path in job_paths:
                job_text = job_path.read_text(encoding="utf-8")
                for resume_path, resume_text in resumes.items():
                    logps[(resume_path, str(job_path))] = matcher.strong_logprob(
                        resume_text, job_text
                    )
            for resume_path in resumes:
                jobs = {
                    j: lp for (r, j), lp in logps.items() if r == resume_path
                }
                probs = torch.softmax(torch.tensor(list(jobs.values())), dim=0)
                best = max(jobs, key=jobs.get)
                for (job_path, lp), p in zip(jobs.items(), probs.tolist()):
                    record = {
                        "resume_file": resume_path,
                        "job_file": job_path,
                        "strong_logprob": lp,
                        "probs": {"best fit": p},
                        "top": "best fit" if job_path == best else None,
                    }
                    out_f.write(json.dumps(record) + "\n")
                    out_f.flush()
        else:
            for job_path in job_paths:
                job_text = job_path.read_text(encoding="utf-8")
                for resume_path, resume_text in resumes.items():
                    criteria = None
                    if mode == "criteria":
                        result = matcher.score_criteria(resume_text, job_text)
                        probs = result["probs"]
                        criteria = result["criteria"]
                    elif mode == "category":
                        probs = matcher.score_category(resume_text, job_text)
                    else:
                        probs = matcher.score(resume_text, job_text)
                    confidence = probs.get("strong match", max(probs.values()))
                    if confidence < args.min_strong:
                        continue
                    record = {
                        "resume_file": resume_path,
                        "job_file": str(job_path),
                        "probs": probs,
                        "top": max(probs, key=probs.get),
                    }
                    if criteria is not None:
                        record["criteria"] = criteria
                    out_f.write(json.dumps(record) + "\n")
                    out_f.flush()
    finally:
        if args.out:
            out_f.close()


if __name__ == "__main__":
    main()

