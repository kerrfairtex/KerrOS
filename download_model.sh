#!/data/data/com.termux/files/usr/bin/bash
cd ~/offline_ai
huggingface-cli download \
  Qwen/Qwen2.5-1.5B-Instruct-GGUF \
  qwen2.5-1.5b-instruct-q4_k_m.gguf \
  --local-dir models/
mv models/qwen2.5-1.5b-instruct-q4_k_m.gguf models/model.gguf 2>/dev/null || true
echo "Done! Run: bash run.sh"
