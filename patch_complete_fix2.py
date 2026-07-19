path = "/data/data/com.termux/files/home/offline_ai/core/complete.py"
with open(path) as f:
    src = f.read()

old = '''        # Repetition guard: if this "continuation" just restates the
        # beginning of what we already have (small-model failure mode),
        # stop here instead of compounding duplicate content.
        if full_response:
            prev_start = full_response[:60].strip().lower()
            chunk_start = chunk[:60].strip().lower()
            if prev_start and chunk_start and prev_start[:40] == chunk_start[:40]:
                break'''

new = '''        # Repetition guard: if a meaningful slice of this continuation
        # already appears anywhere in what we have so far (small-model
        # restating/looping failure mode), stop instead of compounding it.
        if full_response and chunk:
            probe = chunk.strip()[:80].lower()
            if len(probe) >= 30 and probe in full_response.lower():
                break'''

if old in src:
    src = src.replace(old, new)
    with open(path, "w") as f:
        f.write(src)
    print("Patched.")
else:
    print("SKIPPED")
