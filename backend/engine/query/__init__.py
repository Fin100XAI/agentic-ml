"""Query path: structured, deterministic answers to direct questions.

The LLM (or a keyword fallback) emits a typed QueryPlan; a deterministic
interpreter executes it against an artifact frame. No generated code is
ever executed - the plan schema IS the entire expressive surface.
"""
