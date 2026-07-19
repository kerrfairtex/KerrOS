#!/usr/bin/env python3
"""Loads api_config.yaml, checks which env vars are actually set, prints status.
Usage: python3 api_status.py
"""
import os
import yaml

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "api_config.yaml")


def flatten(section, prefix=""):
    """Yield (name, env_var) pairs from a category dict, skipping non-env entries."""
    for name, val in section.items():
        if isinstance(val, dict):
            env = val.get("env") or val.get("api_env") or val.get("pat_env")
            if env:
                yield f"{prefix}{name}", env
            for sub_key in ("endpoint_env", "studio_env", "widget_key_env", "api_key_env"):
                if sub_key in val:
                    yield f"{prefix}{name}.{sub_key.replace('_env','')}", val[sub_key]


def main():
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)

    for category in ("llm_cloud", "llm_local", "vector_db", "database", "storage",
                      "search_and_research", "utility_services", "app_specific"):
        section = cfg.get(category, {})
        print(f"\n[{category}]")
        for name, env in flatten(section):
            set_flag = "OK " if os.environ.get(env) else "MISSING"
            print(f"  {set_flag:8s} {name:<20s} ({env})")


if __name__ == "__main__":
    main()

