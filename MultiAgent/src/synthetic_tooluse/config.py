import os
from dotenv import load_dotenv

load_dotenv()

# We will use litellm for real model calls if API keys are present.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Fallback mode flag
USE_MOCK_LLM = not bool(OPENAI_API_KEY or ANTHROPIC_API_KEY)

# When true, the pipeline executes every planned endpoint in order with grounded args
# (assistant cannot skip steps or batch unrelated tools). Set SYNTH_STRICT_PLAN_EXECUTION=0 to disable.
_STRICT = os.getenv("SYNTH_STRICT_PLAN_EXECUTION", "true").strip().lower()
STRICT_PLAN_EXECUTION = _STRICT in ("1", "true", "yes", "on")

# Default generation models
DEFAULT_GENERATION_MODEL = "gpt-4o-mini" if OPENAI_API_KEY else "mock-generation-model"
DEFAULT_JUDGE_MODEL = "gpt-4o" if OPENAI_API_KEY else "mock-judge-model"

# Paths
ARTIFACT_DIR_DEFAULT = "artifacts"
