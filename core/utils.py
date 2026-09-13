import os
import ssl
import certifi
import requests
from pathlib import Path

def safe_abs_path(path: str, base_dir: str) -> Path:
    """
    Resolve a path to an absolute, canonical form within base_dir.
    Raises ValueError if the resolved path escapes base_dir.
    """
    base = Path(base_dir).resolve()
    target = Path(path)
    
    # If target is relative, join with base
    if not target.is_absolute():
        target = base / target
    
    # Resolve symlinks; strict=False handles non-existent paths
    resolved = target.resolve(strict=False)
    
    # Ensure resolved path is within base_dir
    try:
        common = os.path.commonpath([str(base), str(resolved)])
    except ValueError:
        raise ValueError(f"Path '{path}' escapes base directory '{base_dir}'")
    
    if common != str(base):
        raise ValueError(f"Path '{path}' escapes base directory '{base_dir}'")
    
    return resolved

def get_ssl_context() -> ssl.SSLContext:
    """
    Returns an SSL context that defaults to the system bundle 
    but falls back to the certifi bundle if verification fails.
    """
    ctx = ssl.create_default_context()
    try:
        # Check if default context can verify a common endpoint
        ssl.create_default_context().load_default_certs()
    except ssl.SSLCertVerificationError:
        # Fallback to certifi
        ctx.load_verify_locations(cafile=certifi.where())
    return ctx

def get_session() -> requests.Session:
    """
    Returns a requests session configured with certifi-backed verification.
    """
    session = requests.Session()
    session.verify = certifi.where()
    return session
