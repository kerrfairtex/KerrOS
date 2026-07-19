from execution.sandbox.process_sandbox import ProcessSandbox

class SafeExecutor:
    def __init__(self):
        self.sandbox = ProcessSandbox()

    def execute(self, cmd):
        return self.sandbox.run(cmd)
