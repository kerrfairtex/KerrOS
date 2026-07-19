#!/usr/bin/env python3
"""Loads .env + api_config.yaml, checks which env vars are actually set."""
import os
import yaml
from dotenv import load_dotenv

BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE, ".env"))

CONFIG_PATH = os.path.join(BASE, "api_config.yaml")


def flatten(section, prefix=""):
    for name, val in section.items():
        if isinstance(val, dict):
            env = val.get("env") or val.get("api_env") or val.get("pat_env")
            if env:
                yield f"{prefix}{name}", env
            for key, v in val.items():
                if key.endswith("_env") and key not in ("env",):
                    yield f"{prefix}{name}.{key[:-4]}", v


def main():
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)

    for category in ("llm_cloud", "llm_local", "vector_db", "database", "storage",
                      "search_and_research", "utility_services", "app_specific", "deploy"):
        section = cfg.get(category, {})
        print(f"\n[{category}]")
        for name, env in flatten(section):
            set_flag = "OK " if os.environ.get(env) else "MISSING"
            print(f"  {set_flag:8s} {name:<20s} ({env})")


if __name__ == "__main__":
    main()
