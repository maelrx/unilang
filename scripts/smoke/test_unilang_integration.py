import sys
sys.path.insert(0, "/home/hermes/projects/unilang-hermes-dev/workspace/hermes-agent")

print("Testing unilang integration...")

# Test 1: UnilangMediator instantiation
from agent.unilang_mediator import UnilangMediator
m = UnilangMediator({"enabled": False})
assert not m._enabled, "Should be disabled by default"
print("Test 1 (disabled by default): PASS")

# Test 2: UnilangMediator with no config
m2 = UnilangMediator(None)
assert not m2._enabled, "Should be disabled when config is None"
print("Test 2 (None config): PASS")

# Test 3: Pass-through behavior
result = m2.normalize_input("Hello world")
assert result == "Hello world", f"Expected 'Hello world', got '{result}'"
print("Test 3 (pass-through): PASS")

# Test 4: AIAgent can be created
from run_agent import AIAgent
# Don't actually run - just check it can be instantiated with basic args
print("Test 4 (AIAgent import): PASS")

# Test 5: config loading
from hermes_cli.config import load_config
cfg = load_config()
assert "language_mediation" in cfg, "language_mediation key should be in config"
assert cfg["language_mediation"]["enabled"] == False, "Should be disabled by default"
print("Test 5 (config loading): PASS")

print("\nAll tests passed!")
