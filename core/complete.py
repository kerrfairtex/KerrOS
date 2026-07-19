"""
core/complete.py
Auto-continuation wrapper for offline generation.

Small models + limited max_tokens means long answers (research paper
sections, full code files, detailed reports) get cut off mid-sentence.
This detects truncation and automatically continues generation from
where it stopped, looping until the response is actually finished or
a safety cap is hit.
"""
import re

MAX_CONTINUATIONS = 1  # small model reliability drops sharply after 1 continuation; cap here rather than risk repeated restarts

# Signals that a response ended cleanly (not mid-thought)
END_PUNCT = (".", "!", "?", '"', "'", ")", "]", "}", "```", ":", ";")

def looks_truncated(text):
    """Heuristic: does this look like it was cut off mid-sentence/mid-word?"""
    t = text.rstrip()
    if not t:
        return False
    # Ends mid-word (no trailing space/punct, last char is alnum and text is long)
    if len(t) > 40 and t[-1].isalnum():
        return True
    # Ends with a dangling connector word suggesting more was coming
    dangling = ("and", "but", "or", "the", "a", "an", "to", "of", "with",
                "for", "is", "this", "specifically", "including", "such")
    last_word = re.split(r'\s+', t)[-1].lower().strip(".,;:")
    if last_word in dangling:
        return True
    # Ends with an unclosed code fence (odd number of ``` occurrences)
    if t.count("```") % 2 == 1:
        return True
    return False


def generate_complete(engine, user_message, system=None, history=None,
                       stream=False, max_continuations=MAX_CONTINUATIONS):
    """
    Like engine.generate(), but automatically continues if the response
    looks truncated, stitching continuations together into one complete answer.
    """
    full_response = ""
    current_user_message = user_message
    current_history = list(history or [])

    for i in range(max_continuations + 1):
        chunk = engine.generate(
            user_message=current_user_message,
            system=system,
            history=current_history,
            stream=stream,
        )
        chunk = chunk or ""

        # Repetition guard: slide a window through the new chunk and check
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
                break

        full_response += chunk

        if not looks_truncated(chunk):
            break

        if i == max_continuations:
            break  # hit safety cap, stop even if still truncated

        current_history = current_history + [
            {"role": "user", "content": current_user_message},
            {"role": "assistant", "content": full_response[-800:]},
        ]
        last_words = " ".join(full_response.strip().split()[-8:])
        current_user_message = (
            f"Your previous answer was cut off. It ended with: \"...{last_words}\"\n"
            f"Continue writing the NEXT part only. Do NOT repeat the sentence above. "
            f"Do NOT restart the explanation. Just continue directly from that point."
        )

    return full_response.strip()
