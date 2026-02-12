# scripts/render_architecture.py
import subprocess, pathlib

MERMAID = """
flowchart LR
  intake_agent --> idea_agent
  idea_agent --> elaboration_agent
  elaboration_agent --> optimization_agent
  optimization_agent --> bmc_agent
  bmc_agent --> control_agent
"""

out = pathlib.Path("architecture.svg")
p = subprocess.run(
    ["mmdc", "-i", "-", "-o", str(out)],
    input=MERMAID.encode("utf-8"),
)
print("written:", out)
