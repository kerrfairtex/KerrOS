import ast
import astor
import random
import subprocess
import sys
import os

def mutate_code(source):
    """
    Performs a simple variable renaming mutation.
    In a production agentic system, this would be replaced with 
    LLM-based refactoring or structural logic mutations.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    class Renamer(ast.NodeTransformer):
        def visit_Name(self, node):
            if isinstance(node.ctx, ast.Store):
                node.id = f"{node.id}_{random.randint(1,999)}"
            return node

    mutated = Renamer().visit(tree)
    return astor.to_source(mutated)

def apply_mutation(file_path):
    """
    Applies a mutation, validates syntax, and promotes if stable.
    """
    if not os.path.exists(file_path):
        return False

    with open(file_path, 'r') as f:
        src = f.read()
    
    mutated = mutate_code(src)
    if not mutated:
        return False
        
    tmp = file_path + '.tmp'
    with open(tmp, 'w') as f:
        f.write(mutated)
    
    # 1. Validate Syntax
    try:
        subprocess.check_call([sys.executable, '-m', 'py_compile', tmp])
    except subprocess.CalledProcessError:
        if os.path.exists(tmp):
            os.remove(tmp)
        return False
        
    # 2. In a real 'Self-Refactoring Loop', 
    # we would run unit tests here before os.replace().
    # os.replace(tmp, file_path)
    print(f"Validated mutation for {file_path}. Ready for test-suite integration.")
    return True
