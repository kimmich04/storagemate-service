# 0006. Regex-first parser cascade; NER/LLM reads need human OK
> Status: Accepted
> Date: 2026-11-01

## Context
A fixed syntax (`Nhập|Xuất qty unit item giờ ngày`) is precise and free. Staff still type loosely (no diacritics,
natural phrasing). The project also has a learning goal: train → deploy → flywheel a Vietnamese NER.

## Decision
We will parse with regex → NER (ViDeBERTa-xsmall, ONNX int8, confidence threshold) → LLM structured output
(Pydantic-validated), stopping at the first success. Only regex results write directly; NER/LLM results become
`pending_actions` that the sender must confirm with `OK`. Only human-confirmed samples become training labels;
retraining is batch (Colab, golden-set F1 gate), never realtime.

## Alternatives considered
- LLM-only — cost, latency, unverifiable writes. Regex-only — brittle. Realtime learning — one bad typist poisons the model.

## Consequences
- Regex is the production path; NER reduces LLM calls and is the learning piece.
- Golden set (real messages) stays separate from synthetic training data.
