# ml/ — train NER (chạy trên máy local RTX 4070, không deploy)

Thứ tự:
1. `scripts/build_catalog.py`      → `data/catalog/items.csv`, `data/catalog/units.csv` (lấy từ DataMate + alias tự thêm)
2. `scripts/generate_synthetic.py` → `data/synthetic/*.jsonl` (BIO, 1.000–3.000 câu)
3. `scripts/train_ner.py`          → fine-tune ViDeBERTa-xsmall (HF Trainer, seqeval)
4. `scripts/export_onnx.py`        → `../models/ner/model_quantized.onnx` (Optimum, dynamic int8)
5. `scripts/evaluate.py`           → F1 trên `data/golden/` (tin người thật gõ, KHÔNG dùng để train)

Cài thư viện train: `pip install -e ".[ml]"` (cài torch bản CUDA theo pytorch.org trước).
