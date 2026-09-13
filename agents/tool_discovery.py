import os, hashlib, subprocess, sys, ast, sqlite3, json, asyncio

# Use absolute paths to match project root
BASE_DIR = '/data/data/com.termux/files/home/offline_ai'
DB_PATH = os.path.join(BASE_DIR, 'data/tool_registry.db')
EVENT_LOG = os.path.join(BASE_DIR, 'kernel_events.log')

def checksum(path: str) -> str:
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()

def validate_script(path: str) -> bool:
    """Require `execute()` and `help()` functions."""
    try:
        with open(path, 'r', errors='ignore') as f:
            tree = ast.parse(f.read(), filename=path)
        names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        return {'execute', 'help'}.issubset(names)
    except Exception as e:
        return False

async def sandbox_load(path: str) -> bool:
    """Run the script in a child process to guard against import errors."""
    try:
        # Capture stderr to see why it fails
        proc = await asyncio.create_subprocess_exec(
            sys.executable, path, '--help',
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            print(f"Sandbox failed for {path} (Exit {proc.returncode}): {stderr.decode().strip()[:100]}")
        return proc.returncode == 0
    except Exception as e:
        print(f"Sandbox exception for {path}: {e}")
        return False

async def register_tool(path: str) -> bool:
    if not validate_script(path):
        return False
    if not await sandbox_load(path):
        return False

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        '''CREATE TABLE IF NOT EXISTS tools
           (name TEXT PRIMARY KEY,
            path TEXT,
            checksum TEXT)'''
    )
    cur.execute(
        '''INSERT OR REPLACE INTO tools VALUES (?,?,?)''',
        (os.path.basename(path), path, checksum(path))
    )
    conn.commit()
    conn.close()

    await notify_kernel('tool_added', path)
    return True

async def notify_kernel(event: str, payload: str):
    msg = json.dumps({'event': event, 'payload': payload})
    with open(EVENT_LOG, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')

async def scan_and_register(base_dir: str):
    if not os.path.exists(base_dir):
        print(f"Skipping: {base_dir} (not found)")
        return
    for root, _, files in os.walk(base_dir):
        for f in files:
            if f.endswith('.py') and f != '__init__.py':
                path = os.path.join(root, f)
                if await register_tool(path):
                    print(f"Registered: {f}")
                else:
                    print(f"Failed to register: {f}")

if __name__ == '__main__':
    # Point at the directories
    dirs = [os.path.join(BASE_DIR, 'wrapped_tools')]
    
    async def main():
        for d in dirs:
            await scan_and_register(d)
    
    asyncio.run(main())
    print('🔍 Tool discovery finished')
