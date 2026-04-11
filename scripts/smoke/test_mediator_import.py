import sys
sys.path.insert(0, "/home/hermes/projects/unilang-hermes-dev/workspace/hermes-agent")

from agent.unilang_mediator import UnilangMediator

m = UnilangMediator()
print("Mediator loaded OK, enabled:", m._enabled)

m_enabled = UnilangMediator({"enabled": True})
print("Mediator with enabled=True loaded OK, enabled:", m_enabled._enabled)
print("Runtime:", m_enabled._runtime)
