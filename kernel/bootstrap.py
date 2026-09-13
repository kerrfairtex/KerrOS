"""
kernel/bootstrap.py
===================
Shim: proposed future path for kernel bootstrap.
Current implementation: kernel/boot.py
"""

from kernel.boot import Kernel, kernel_boot

__all__ = ["Kernel", "kernel_boot"]
