path = "/data/data/com.termux/files/home/offline_ai/core/multi_api.py"
with open(path) as f:
    src = f.read()

old = '''    ALL_APIS = [
        ("Groq",             lambda messages, mt: call_groq(messages, max_tokens=mt)),
        ("NVIDIA-Llama405B", lambda messages, mt: call_nvidia(messages, max_tokens=mt)),
        ("DeepSeek",         lambda messages, mt: call_deepseek(messages, mt)),
        ("Cohere",           lambda messages, mt: call_cohere(messages, mt)),
        ("OpenRouter",       lambda messages, mt: call_openrouter(messages, max_tokens=mt)),
        ("HuggingFace",      lambda messages, mt: call_huggingface(messages, max_tokens=mt)),
        ("Gemini",           lambda messages, mt: call_gemini(messages, mt)),
    ]'''

new = '''    ALL_APIS = [
        ("Groq",             lambda messages, mt: call_groq(messages, max_tokens=mt)),
        ("Anthropic",        lambda messages, mt: call_anthropic(messages, max_tokens=mt)),
        ("NVIDIA-Llama405B", lambda messages, mt: call_nvidia(messages, max_tokens=mt)),
        ("DeepSeek",         lambda messages, mt: call_deepseek(messages, mt)),
        ("Cohere",           lambda messages, mt: call_cohere(messages, mt)),
        ("OpenRouter",       lambda messages, mt: call_openrouter(messages, max_tokens=mt)),
        ("HuggingFace",      lambda messages, mt: call_huggingface(messages, max_tokens=mt)),
        ("Gemini",           lambda messages, mt: call_gemini(messages, mt)),
    ]'''

if old in src:
    src = src.replace(old, new)
    with open(path, "w") as f:
        f.write(src)
    print("Patched ALL_APIS.")
else:
    print("SKIPPED")

old2 = '''        elif task == "reasoning":
            chain = [
                ("Cohere",           lambda: call_cohere(messages, max_tokens)),
                ("OpenRouter",       lambda: call_openrouter(messages, max_tokens=max_tokens)),
                ("Groq",             lambda: call_groq(messages, max_tokens=max_tokens)),
            ]'''
new2 = '''        elif task == "reasoning":
            chain = [
                ("Anthropic",        lambda: call_anthropic(messages, max_tokens=max_tokens)),
                ("Cohere",           lambda: call_cohere(messages, max_tokens)),
                ("OpenRouter",       lambda: call_openrouter(messages, max_tokens=max_tokens)),
                ("Groq",             lambda: call_groq(messages, max_tokens=max_tokens)),
            ]'''

if old2 in src:
    src = src.replace(old2, new2)
    with open(path, "w") as f:
        f.write(src)
    print("Patched reasoning chain.")
else:
    print("SKIPPED reasoning chain")
