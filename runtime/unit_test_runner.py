import subprocess
import json
import os
import sys

def run_tests(test_dir='/data/data/com.termux/files/home/offline_ai/tests'):
    """
    Runs tests using pytest and checks if all passed.
    Note: Requires pytest and pytest-json-report to be installed.
    """
    report_file = '/data/data/com.termux/files/home/offline_ai/report.json'
    
    # Run pytest
    cmd = [sys.executable, '-m', 'pytest', test_dir, f'--json-report', f'--json-report-file={report_file}']
    subprocess.run(cmd, capture_output=True)
    
    if not os.path.exists(report_file):
        return False
        
    with open(report_file, 'r') as f:
        data = json.load(f)
        
    passed = data['summary'].get('passed', 0)
    total = data['summary'].get('total', 0)
    
    # Clean up
    os.remove(report_file)
    
    return passed == total and total > 0
