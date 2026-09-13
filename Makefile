.PHONY: help install model smoke attack defense dev ui

help:  ## Show the available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  make %-10s %s\n", $$1, $$2}'

install:  ## Install dependencies with uv
	uv sync

model:  ## Start Docker and pull the small local model
	docker desktop start
	docker model pull ai/qwen2.5:1.5B-F16

smoke:  ## Offline sanity checks (no model needed)
	uv run python -m lab.smoke

attack:  ## Run the attack scenario (direct + indirect)
	uv run python -m lab.attack

defense:  ## Run all five defenses
	uv run python -m lab.defense

dev:  ## Drive the agent yourself in LangGraph Studio
	uv run langgraph dev

ui:  ## Run the agent from the LangServe browser playground
	uv run uvicorn lab.serve:app --reload
