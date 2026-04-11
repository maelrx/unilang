import sys
sys.path.insert(0, "/home/hermes/projects/unilang-hermes-dev/workspace/hermes-agent")
try:
    from agent.unilang_mediator import UnilangMediator
    print("UnilangMediator: OK")
except Exception as e:
    print(f"UnilangMediator: FAILED - {e}")

try:
    from run_agent import AIAgent
    print("AIAgent: OK")
except Exception as e:
    print(f"AIAgent: FAILED - {e}")

try:
    from hermes_cli.config import load_config
    print("load_config: OK")
except Exception as e:
    print(f"load_config: FAILED - {e}")
