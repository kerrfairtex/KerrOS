#!/usr/bin/env python3
"""
Quick test to verify the offline AI system works after our fix.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.engine import LLMEngine

def test_system():
    print("=== Testing KerrOS Offline AI System ===")
    
    # Create engine
    engine = LLMEngine()
    
    # Test a simple query
    print("\nTesting with query: 'What is artificial intelligence?'")
    try:
        response = engine.chat("What is artificial intelligence?")
        print(f"Response: {response}")
        print("✓ System is working!")
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_system()
    sys.exit(0 if success else 1)