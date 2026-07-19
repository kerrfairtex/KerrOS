"""
LEGACY COMPLETION ADAPTER
=========================

Phase 8.8

Compatibility bridge between existing
engine.generate() calls and the new
Completion Runtime.

Purpose:
- Preserve old agents
- Enable gradual migration
- Centralize completion tracking

Does not modify existing engines.
"""

from __future__ import annotations



class LegacyCompletionAdapter:


    def __init__(self):

        self.runtime = None

        self.enabled = True

        self._load()



    def _load(self):

        try:
            from core.completion_runtime_api import runtime_api
            self.runtime = runtime_api

        except Exception:

            self.runtime = None



    def generate(
        self,
        engine,
        user_message,
        system=None,
        history=None,
        stream=False,
        metadata=None,
    ):


        if (
            self.enabled
            and self.runtime
        ):

            try:

                result = self.runtime.execute(
                    agent="legacy",
                    engine=engine,
                    message=user_message,
                    system=system,
                    history=history,
                    stream=stream,
                    metadata=metadata,
                )


                if isinstance(result, dict):

                    return result.get(
                        "response",
                        result
                    )


                return result


            except Exception:

                # Safety fallback
                pass



        # Original behavior fallback

        return engine.generate(
            user_message=user_message,
            system=system,
            history=history,
            stream=stream,
        )



adapter = LegacyCompletionAdapter()


def generate(*args, **kwargs):

    return adapter.generate(
        *args,
        **kwargs
    )

