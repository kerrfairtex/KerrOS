#!/usr/bin/env python3
"""
Comprehensive fix script for offline_ai import scripts.
Addresses both import API updates and hardcoded path fixes.
"""
import re
import os
from pathlib path = Path

def fix_import_script(script_name):
    """Fix a single import script"""
    print(f"🔧 Processing {script_name}...")
    
    script_path = Path.home() / "offline_ai" / script_name
    if not script_path.exists():
        print(f"  ❌ {script_name} not found")
        return False
    
    content = script_path.read_text()
    
    # Track what we're changing
    changes = []
    
    # Fix 1: Update import statements
    old_imports = [
        "from rag.store import _load, _save, _chunk, _keywords",
        "from rag.store import _load, _save, _chunk, _keywords, _category_from_source",
    ]
    
    new_imports = [
        "from rag.store import ingest_text, ingest_file, search, search_fts, search_by_category, search_multi_category",
        "from rag.store import ingest_text, ingest_file, search, search_fts, search_by_category, search_multi_category, ingest_file",
    ]
    
    for old_import, new_import in zip(old_imports, new_imports):
        if old_import in content:
            content = content.replace(old_import, new_import)
            changes.append(f"  - Updated imports: {old_import} → {new_import}")
    
    # Fix 2: Replace hardcoded paths with environment variables
    # Pattern to match: VAR = Path.home() / "storage/external-1/offline_ai_knowledge/..."
    path_pattern = r'(\w+)\s*=\s*Path\.home\(\)\s*/\s*"storage/external-1/offline_ai_knowledge'
    
    def replace_path(match):
        var_name = match.group(1)
        
        # Map variable names to environment variables and fallback paths
        env_var_map = {
            "CAPEC": ("CAPEC_PATH", "test_capec.xml"),
            "CISA": ("CISA_PATH", "test_cisa.json"),
            "ROOT": ("ROOT_PATH", "data/raw"),
            "CWE": ("CWE_PATH", "data/raw/cwe.xml"),
            "ATTACK": ("MITRE_ATTACK_PATH", "data/raw/enterprise-attack.json"),
            "NIST": ("NIST_PATH", "data/raw/nist"),
            "OWASP": ("OWASP_PATH", "data/raw/owasp"),
            "SIGMA": ("SIGMA_PATH", "data/raw/sigma"),
            "YARA": ("YARA_PATH", "data/raw/yara"),
        }
        
        if var_name in env_var_map:
            env_var, fallback = env_var_map[var_name]
            return f"{var_name} = os.environ.get('{env_var}') or Path.home() / 'offline_ai' / '{fallback}'"
        else:
            return match.group(0)  # Keep original if no mapping
    
    # Apply path replacements
    lines = content.split('\n')
    new_lines = []
    for line in lines:
        if "storage/external-1/offline_ai_knowledge" in line and "=" in line:
            match = re.search(path_pattern, line)
            if match:
                replacement = replace_path(match)
                new_line = line.replace(match.group(0), replacement)
                new_lines.append(new_line)
                changes.append(f"  - Updated path: {match.group(0)} → {replacement}")
                continue
        new_lines.append(line)
    
    content = '\n'.join(new_lines)
    
    # Fix 3: Update ingest_file calls to use current API
    content = content.replace("ingest_file(", "ingest_file(")
    
    # Fix 4: Update old function calls to new API
    content = content.replace("_load()", "search('manual')")
    content = content.replace("_save(store)", "")
    content = content.replace("_chunk(text)", "ingest_text(text, 'manual')")
    
    # Write back to file
    script_path.write_text(content)
    
    if changes:
        print(f"  ✅ {script_name} fixed with {len(changes)} changes")
        for change in changes:
            print(f"     {change}")
    else:
        print(f"  ✅ {script_name} already up to date")
    
    return True

def main():
    print("🔧 Comprehensive Import Script Fix")
    print("=" * 50)
    
    # List of import scripts to fix
    import_scripts = [
        "import_capec.py",
        "import_cisa.py", 
        "import_cve.py",
        "import_cwe.py",
        "import_mitre_attack.py",
        "import_nist.py",
        "import_owasp.py",
        "import_sigma.py",
        "import_yara.py"
    ]
    
    success_count = 0
    for script in import_scripts:
        if fix_import_script(script):
            success_count += 1
    
    print("=" * 50)
    print(f"✅ Fix complete: {success_count}/{len(import_scripts)} scripts processed")
    print("\nNext steps:")
    print("1. Test each script to ensure they work correctly")
    print("2. Run imports to verify functionality")
    print("3. Check for any remaining issues")

if __name__ == "__main__":
    main()
PYEOF
# Set correct path for writing

cat > ~/offline_ai/fix_import_scripts.py << 'PYEOF'
#!/usr/bin/env python3
"""
Comprehensive fix script for offline_ai import scripts.
Updates import API and replaces hardcoded paths with environment variables.
"""
import re
import os
from pathlib import Path

ROOT = Path.home() / "offline_ai"

# Mapping of script names to their specific fixes
SCRIPT_FIXES = {
    "import_capec.py": {
        "old_import": "from rag.store import _load, _save, _chunk, _keywords",
        "new_import": "from rag.store import ingest_text",
        "old_pattern": r'CAPEC = Path\.home\(\) "/storage/external-1/offline_ai_knowledge/cybersecurity/capec/capec\.xml"',
        "new_line": "CAPEC = os.environ.get('CAPEC_PATH') or Path.home() / 'offline_ai' / 'test_capec.xml'"
    },
    "import_cisa.py": {
        "old_import": "from rag.store import _load, _save, _chunk, _keywords",
        "new_import": "from rag.store import ingest_text",
        "old_pattern": r'CISA = Path\.home\(\) "/storage/external-1/offline_ai_knowledge/cybersecurity/cisa/known_exploited_vulnerabilities\.json"',
        "new_line": "CISA = os.environ.get('CISA_PATH') or Path.home() / 'offline_ai' / 'test_cisa.json'"
    },
    "import_cve.py": {
        "old_import": "from rag.store import _load, _save, _chunk, _keywords, _category_from_source",
        "new_import": "from rag.store import ingest_file",
        "old_pattern": r'ROOT = Path\.home\(\) "/storage/external-1/offline_ai_knowledge/cybersecurity/cve/cvelistV5/cves"',
        "new_line": "ROOT = os.environ.get('ROOT_PATH') or Path.home() / 'offline_ai' / 'data/raw/cve'"
    },
    "import_cwe.py": {
        "old_import": "from rag.store import _load, _save, _chunk, _keywords",
        "new_import": "from rag.store import ingest_file",
        "old_pattern": r'CWE = Path\.home\(\) "/storage/external-1/offline_ai_knowledge/cybersecurity/cwe/cwec_v4\.20\.xml"',
        "new_line": "CWE = os.environ.get('CWE_PATH') or Path.home() / 'offline_ai' / 'data/raw/cwe.xml'"
    },
    "import_mitre_attack.py": {
        "old_import": "from rag.store import ingest_text",
        "new_import": "from rag.store import ingest_text",
        "old_pattern": r'ATTACK = Path\.home\(\) "/storage/external-1/offline_ai_knowledge/cybersecurity/mitre_attack/enterprise-attack\.json"',
        "new_line": "ATTACK = os.environ.get('MITRE_ATTACK_PATH') or Path.home() / 'offline_ai' / 'data/raw/enterprise-attack.json'"
    },
    "import_nist.py": {
        "old_import": "from rag.store import ingest_text",
        "new_import": "from rag.store import ingest_file",
        "old_pattern": r'ROOT = Path\.home\(\) "/storage/external-1/offline_ai_knowledge/cybersecurity/nist"',
        "new_line": "ROOT = os.environ.get('ROOT_PATH') or Path.home() / 'offline_ai' / 'data/raw/nist'"
    },
    "import_owasp.py": {
        "old_import": "from rag.store import ingest_file",
        "new_import": "from rag.store import ingest_file",
        "old_pattern": r'"~/storage/external-1/offline_ai_knowledge/cybersecurity/owasp"',
        "new_line": "os.environ.get('OWASP_PATH') or Path.home() / 'offline_ai' / 'data/raw/owasp"
    },
    "import_sigma.py": {
        "old_import": "from rag.store import _load, _save, _chunk, _keywords",
        "new_import": "from rag.store import ingest_text",
        "old_pattern": r'ROOT = Path\.home\(\) "/storage/external-1/offline_ai_knowledge/cybersecurity/sigma"',
        "new_line": "ROOT = os.environ.get('ROOT_PATH') or Path.home() / 'offline_ai' / 'data/raw/sigma'"
    },
    "import_yara.py": {
        "old_import": "from rag.store import _load, _save, _chunk, _keywords",
        "new_import": "from rag.store import ingest_file",
        "old_pattern": r'ROOT = Path\.home\(\) "/storage/external-1/offline_ai_knowledge/cybersecurity/yara"',
        "new_line": "ROOT = os.environ.get('ROOT_PATH') or Path.home() / 'offline_ai' / 'data/raw/yara'"
    }
}

def fix_script(script_name):
    """Fix a single import script"""
    print(f"🔧 Fixing {script_name}...")
    
    script_path = ROOT / script_name
    if not script_path.exists():
        print(f"  ❌ {script_name} not found")
        return False
    
    content = script_path.read_text()
    changes = []
    
    # Fix import statements
    for old, new in SCRIPT_FIXES[script_name]["old_import"].items():
        if old in content:
            content = content.replace(old, new)
            changes.append(f"  - Updated import: {old}")
    
    # Fix path assignments
    old_pattern = SCRIPT_FIXES[script_name]["old_pattern"]
    if old_pattern in content:
        new_line = SCRIPT_FIXES[script_name]["new_line"]
        content = content.replace(old_pattern, new_line)
        changes.append(f"  - Updated path: {old_pattern}")
    
    # Add imports if needed
    if "import os" not in content:
        content = "import os\n" + content
    if "from pathlib import Path" not in content:
        content = "from pathlib import Path\n" + content
    
    # Write back
    script_path.write_text(content)
    
    if changes:
        print(f"  ✅ {script_name} fixed")
        for change in changes:
            print(f"     {change}")
    else:
        print(f"  ✅ {script_name} already up to date")
    
    return True

def main():
    print("🔧 Fixing All Import Scripts")
    print("=" * 50)
    
    success_count = 0
    for script in SCRIPT_FIXES.keys():
        if fix_script(script):
            success_count += 1
    
    print("=" * 50)
    print(f"✅ Fix complete: {success_count}/{len(SCRIPT_FIXES)} scripts processed")
    print("\nNext steps:")
    print("1. Test each script to ensure they work correctly")
    print("2. Run imports to verify functionality")
    print("3. Check for any remaining issues")

if __name__ == "__main__":
    main()
PYEOF
