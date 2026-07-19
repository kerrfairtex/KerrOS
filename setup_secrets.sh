#!/usr/bin/env bash
# Run from inside ~/offline_ai :  bash setup_secrets.sh
set -e

echo "== Step 1: confirm/init git repo =="
if [ ! -d .git ]; then
    echo "No .git found — initializing repo here in $(pwd)"
    git init
else
    echo "Repo already initialized."
fi

echo "== Step 2: write .gitignore =="
cat > .gitignore << 'EOF'
.env
.env.*
!.env.example
*.key
*.pem
*.p12
*.pfx
id_rsa*
id_ed25519*
*.ppk
known_hosts
credentials.json
service-account*.json
*serviceaccount*.json
secrets.json
secrets.yaml
secrets.yml
secrets.toml
.streamlit/secrets.toml
config/secrets.py
**/secrets/
*_credentials*
*.session
sessions/
*.cookie
cookies.txt
.netrc
.npmrc
.pypirc
runtime/*.db
runtime/logs/
*.log
data/vector_store/
data/rag_cache/
models/*.gguf
models/*.bin
models/*.safetensors
__pycache__/
*.pyc
.venv/
venv/
*.egg-info/
.pytest_cache/
.mypy_cache/
EOF

echo "== Step 3: write make_env_example.sh =="
cat > make_env_example.sh << 'EOF'
#!/usr/bin/env bash
set -euo pipefail
SRC="${1:-.env}"
OUT="${2:-.env.example}"
if [ ! -f "$SRC" ]; then
    echo "No $SRC found — nothing to do."
    exit 0
fi
grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$SRC" | sed -E 's/^([A-Za-z_][A-Za-z0-9_]*)=.*/\1=/' > "$OUT"
echo "Wrote $OUT:"
cat "$OUT"
EOF
chmod +x make_env_example.sh

echo "== Step 4: write pre-commit hook into .git/hooks/ =="
mkdir -p .git/hooks
cat > .git/hooks/pre-commit << 'EOF'
#!/usr/bin/env bash
set -euo pipefail
if command -v gitleaks >/dev/null 2>&1; then
    echo "[pre-commit] running gitleaks..."
    gitleaks protect --staged --verbose
    exit $?
fi
echo "[pre-commit] gitleaks not found, using fallback regex scan..."
STAGED_DIFF=$(git diff --cached -U0)
FOUND=0
check() {
    local label="$1" pattern="$2"
    if echo "$STAGED_DIFF" | grep -Eq "$pattern"; then
        echo "  x possible $label detected in staged changes"
        FOUND=1
    fi
}
check "AWS access key"        "AKIA[0-9A-Z]{16}"
check "generic API key"       "(api[_-]?key|apikey)['\"]?\s*[:=]\s*['\"][A-Za-z0-9_\-]{20,}"
check "Groq/OpenAI-style key" "(sk|gsk|groq)-[A-Za-z0-9]{20,}"
check "private key header"    "-----BEGIN (RSA|EC|OPENSSH|DSA) PRIVATE KEY-----"
check "bearer token"          "Bearer\s+[A-Za-z0-9_\-\.]{20,}"
check ".env-style secret"     "^\+(SECRET|TOKEN|PASSWORD|API_KEY)[A-Z_]*\s*="
check "Supabase/DB URL w/ pw" "postgres(ql)?://[^:]+:[^@]+@"
if [ "$FOUND" -eq 1 ]; then
    echo
    echo "[pre-commit] BLOCKED: possible secret in staged changes."
    exit 1
fi
echo "[pre-commit] no obvious secrets found."
exit 0
EOF
chmod +x .git/hooks/pre-commit

echo "== Step 5: TEST — confirm the hook actually blocks a fake secret =="
echo 'GROQ_API_KEY="gsk-THISISAFAKETESTKEY1234567890abcdef"' > .secret_test_file
git add .secret_test_file
if git commit -m "test commit" > /tmp/hook_test_output.txt 2>&1; then
    echo "!! TEST FAILED: the hook did NOT block a fake secret. Check /tmp/hook_test_output.txt"
    git reset --soft HEAD~1 2>/dev/null || true
else
    echo "OK: hook correctly blocked the fake secret. Output was:"
    cat /tmp/hook_test_output.txt
fi
git reset .secret_test_file 2>/dev/null || true
rm -f .secret_test_file

echo
echo "== Done. Persist the Go PATH so gitleaks survives new terminal sessions =="
if ! grep -q 'go/bin' ~/.bashrc 2>/dev/null; then
    echo 'export PATH=$PATH:~/go/bin' >> ~/.bashrc
    echo "Added ~/go/bin to ~/.bashrc — run: source ~/.bashrc"
else
    echo "~/go/bin already in ~/.bashrc"
fi
