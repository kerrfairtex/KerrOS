import os
import sys
from pathlib import Path

# Add project root to path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from core.logger import init_logging
from core.adaptive_engine import AdaptiveEngine
import logging

def run_health_check():
    init_logging(debug=True)
    logger = logging.getLogger("watchdog")
    
    try:
        engine = AdaptiveEngine()
        engine.init_offline()
        output = engine.chat("/health")
        logger.info(f"Health Check: {output}")
        print(f"Health Check Success: {output}")
    except Exception as e:
        logger.error(f"Health Check Failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_health_check()
