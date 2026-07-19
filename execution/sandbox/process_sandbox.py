import subprocess

class ProcessSandbox:
    def run(self, command):
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
                text=True
            )

            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "code": result.returncode
            }

        except Exception as e:
            return {"error": str(e)}
