# ── /react fix ────────────────────────────────────────────
# Replace the /react block in chat.py with this:

        elif user.startswith("/react ") or user.startswith("agent:"):
            from agents.react import ReactAgent
            task = user.replace("/react ","").replace("agent:","").strip()
            if not task:
                print(f"  {RE}Usage: /react <task>{R}")
            else:
                agent = ReactAgent(engine)
                spinner.stop()
                result = agent.run(task, stream=True)
                divider(); ai_header(mode); typewrite(result); divider()
                clean_result = result.strip()
                for tok in ["<|im_start|>","<|im_end|>","<|endoftext|>"]:
                    clean_result = clean_result.replace(tok,"")
                if clean_result and len(clean_result) < 2000:
                    add_message("assistant", clean_result)

# ── /analyze fix ───────────────────────────────────────────
# Replace the /analyze block with this:

        elif user.startswith("/analyze"):
            from prompts.system import ANALYST_PROMPT
            target = user.replace("/analyze","").strip()
            if not target:
                print(f"  {RE}Usage: /analyze <describe your system>{R}")
            else:
                spinner.label="Analyzing"
                spinner.start()
                if engine.current_mode=="online":
                    response=engine.generate(target,system=ANALYST_PROMPT,stream=False)
                else:
                    from prompts.system import ANALYST_PROMPT
                    aprompt=engine._offline._build_prompt(ANALYST_PROMPT,target)
                    response=engine.generate(aprompt,stream=False)
                spinner.stop()
                divider(); ai_header(mode); typewrite(response); divider()
                clean_resp = response.strip()
                for tok in ["<|im_start|>","<|im_end|>","<|endoftext|>"]:
                    clean_resp = clean_resp.replace(tok,"")
                if clean_resp and len(clean_resp) < 2000:
                    add_message("assistant", clean_resp)

# ── main else fix ──────────────────────────────────────────
# Replace the else block with this:

        else:
            extract_and_learn(user)
            add_message("user", user)
            domain = detect_domain(user)
            if domain: print(f"  {PU}◈ Domain: {domain}{R}")

            tool_result = None
            tool, args = detect_tool(user)
            if tool:
                print(f"  {GR}◈ Tool: {tool}{R}")
                spinner.label="Executing"
                spinner.start()
                tool_result = run_tool(tool, args)
                spinner.stop()
                divider()
                for line in tool_result.split("\n"):
                    print(f"  {GY}{line}{R}")
                divider()

            from prompts.system import SYSTEM_PROMPT
            spinner.label="Thinking"
            spinner.start()

            system_p, user_p = build_chat(user, tool_result=tool_result, domain=domain)

            # Use last 2 clean turns only
            raw_hist = get_history(2)
            clean_hist = []
            for m in raw_hist:
                c = m.get("content","").strip()
                bad = ["[Domain:","[Tool output]","Analyze the tool",
                       "<|im_start|>","User: ","Assistant: ",
                       "PING ","bytes from","icmp_seq","packets transmitted"]
                if c and len(c)>3 and len(c)<500 and not any(b in c for b in bad):
                    clean_hist.append({"role":m["role"],"content":c})

            response = engine.generate(
                user_message=user_p,
                system=system_p,
                history=clean_hist,
                stream=False
            )

            spinner.stop()

            # Strip leaked ChatML tokens
            for tok in ["<|im_start|>","<|im_end|>","<|endoftext|>"]:
                response = response.replace(tok,"")
            # Strip thinking artifacts
            if "Now give your final answer:" in response:
                response = response.split("Now give your final answer:")[-1]
            if "[Your reasoning:" in response:
                response = response.split("]")[-1]
            response = response.strip()

            divider(); ai_header(mode); typewrite(response); divider()

            # Save clean responses — raised cap to 2000
            clean_resp = response.strip()
            if clean_resp and len(clean_resp) < 2000:
                add_message("assistant", clean_resp)
