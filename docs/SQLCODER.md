# SQLCoder local NL→SQL (Defog)

MarketMind AI uses [Defog SQLCoder](https://github.com/defog-ai/sqlcoder) as the **primary local** natural-language → SQL generator on Apple Silicon / local servers. DuckDB remains the execution source of truth.

## Why llama.cpp (not Transformers) on Mac

Defog’s own install notes recommend:

- **NVIDIA GPU (≥16GB)** → `sqlcoder[transformers]`
- **Apple Silicon** → `CMAKE_ARGS="-DLLAMA_METAL=on"` / Metal llama.cpp (quantized GGUF)

This Mac (Apple M2, 8GB unified memory) cannot host full fp16 7B weights comfortably. The integration therefore defaults to **llama.cpp + Metal** with `sqlcoder-7b-2.Q3_K_S.gguf` (~3GB).

## What is sent to the model

Only:

1. DuckDB schema as `CREATE TABLE` DDL (tiny type-hint samples optional)
2. Structured semantic requirements / question IR

CSV row payloads are **not** sent.

## Pipeline position

```
pattern / deterministic SIMPLE fast-paths
        ↓ (miss)
local SQLCoder  → schema validate → requirement coverage
        ↓ (fail / disabled)
Groq → Gemini API fallback (only if keys configured)
        ↓
deterministic SQL templates
        ↓
DuckDB execute (existing sandbox + validator + report grounding)
```

Existing result validation, requirement coverage, hallucination protection, and read-only SQL guards are unchanged.

## Configuration (env — never hardcode secrets)

| Variable | Default | Purpose |
|---|---|---|
| `SQLCODER_ENABLED` | `auto` | `true`/`false`; `auto` = on locally, off on Vercel |
| `SQLCODER_PREFER_OVER_API` | `true` | Try local model before Groq/Gemini |
| `SQLCODER_MODEL_PATH` | (empty) | Local `.gguf` path |
| `SQLCODER_HF_REPO` | `MaziyarPanahi/sqlcoder-7b-2-GGUF` | Hub repo |
| `SQLCODER_HF_FILE` | `sqlcoder-7b-2.Q3_K_S.gguf` | Quantized weights |
| `SQLCODER_N_GPU_LAYERS` | `99` on Darwin arm64 | Metal offload |
| `SQLCODER_N_CTX` | `2048` | Context window |
| `HF_TOKEN` | (optional) | Hub auth / rate limits |

## Install

```bash
# Apple Silicon (Metal)
CMAKE_ARGS="-DGGML_METAL=on" pip install "llama-cpp-python>=0.2.90" huggingface-hub

# One-time model download
./scripts/download_sqlcoder.sh
```

## Previous vs new NL→SQL path

| | Previous | Now |
|---|---|---|
| Primary SQL generator | Groq → Gemini API | Local Defog SQLCoder (llama.cpp/Metal) |
| Schema sent | LLM-friendly text + samples | CREATE TABLE DDL (+ tiny samples) |
| CSV rows to model | No | Still no |
| Pre-exec schema gate | Sandbox only (quoted cols) | Codegen + sandbox; **quoted + unquoted** |
| Model lifecycle | N/A (API) | Singleton, optional warmup, timeout |
| Fallback | Deterministic templates | SQLCoder → API → deterministic |
| Cloud deploy | API keys | `SQLCODER_ENABLED=false` on Render (free tier) |

