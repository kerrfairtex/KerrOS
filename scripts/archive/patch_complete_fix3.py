path = "/data/data/com.termux/files/home/offline_ai/core/complete.py"
with open(path) as f:
    src = f.read()

old = '''        # Repetition guard: if a meaningful slice of this continuation
        # already appears anywhere in what we have so far (small-model
        # restating/looping failure mode), stop instead of compounding it.
        if full_response and chunk:
            probe = chunk.strip()[:80].lower()
            if len(probe) >= 30 and probe in full_response.lower():
                break'''

new = '''        # Repetition guard: slide a window through the new chunk and check
        # if any sizeable slice of it already exists in what we have so far
        # (small-model restating/looping failure mode). Catches overlaps that
        # aren't aligned to the very start of the chunk.
        if full_response and chunk:
            c_low = chunk.strip().lower()
            f_low = full_response.lower()
            window = 40
            found_repeat = False
            for start in range(0, max(1, len(c_low) - window), 10):
                slice_ = c_low[start:start+window]
                if len(slice_) >= window and slice_ in f_low:
                    found_repeat = True
                    break
            if found_repeat:
                break'''

if old in src:
    src = src.replace(old, new)
    with open(path, "w") as f:
        f.write(src)
    print("Patched.")
else:
    print("SKIPPED")
