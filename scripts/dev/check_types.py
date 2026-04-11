import unilang.types as t
items = [x for x in dir(t) if not x.startswith("_")]
print("types.py exports:")
for item in sorted(items):
    print(f"  {item}")
