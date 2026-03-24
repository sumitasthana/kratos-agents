# prompts/

This directory contains all LLM system prompts used by kratos-agents, extracted from
source code into standalone YAML files.  Keeping prompts here makes them easy to diff,
review in PRs, and update without touching agent logic.

---

## Schema

Each file follows this shape:

```yaml
id: <short_snake_case_id>           # e.g. root_cause_spark
description: <one line>             # what this prompt is for
source_file: <relative path>        # file where the prompt was originally inlined
agent: <ClassName>                  # agent class that uses this prompt
type: <system|user|tool|example>    # pick the most appropriate
content: |
  <full prompt text, verbatim>
```

### Fields

| Field | Required | Description |
|---|---|---|
| `id` | yes | Stable snake_case identifier. Must match the YAML filename (without `.yaml`). |
| `description` | yes | One-line human-readable summary. |
| `source_file` | yes | Repo-relative path of the agent/module that uses this prompt. |
| `agent` | yes | Python class name (or module name) that owns the prompt. |
| `type` | yes | `system` — injected as the LLM system role.<br>`user` — a user-turn template.<br>`tool` — structured tool/function calling instructions.<br>`example` — few-shot example text. |
| `content` | yes | Full verbatim prompt text. Must use YAML literal-block scalar (`|`) to preserve newlines. **Never truncate.** |

---

## Current prompts

| ID | Agent | Type | YAML file |
|---|---|---|---|
| `root_cause_spark` | `RootCauseAgent` | system | [root_cause_spark.yaml](root_cause_spark.yaml) |
| `root_cause_grc` | `RootCauseAgent` | system | [root_cause_grc.yaml](root_cause_grc.yaml) |
| `query_understanding` | `QueryUnderstandingAgent` | system | [query_understanding.yaml](query_understanding.yaml) |
| `git_diff_dataflow` | `GitDiffDataFlowAgent` | system | [git_diff_dataflow.yaml](git_diff_dataflow.yaml) |
| `lineage_extraction` | `LineageExtractionAgent` | system | [lineage_extraction.yaml](lineage_extraction.yaml) |
| `infra_analyzer` | `InfraAnalyzerAgent` | system | [infra_analyzer.yaml](infra_analyzer.yaml) |
| `change_analyzer` | `ChangeAnalyzerAgent` | system | [change_analyzer.yaml](change_analyzer.yaml) |

---

## How prompts are loaded

The helper module [`src/prompt_loader.py`](../src/prompt_loader.py) handles I/O:

```python
from src.prompt_loader import load_prompt_content, load_prompt, list_prompts

# Most common — returns just the content string
SYSTEM_PROMPT = load_prompt_content("root_cause_spark")

# Returns the full record dict (id, description, agent, type, content, …)
record = load_prompt("root_cause_spark")

# List all available prompt IDs
ids = list_prompts()
```

Results are cached via `functools.lru_cache`, so each YAML file is read only once
per process lifetime.

---

## How to add a new prompt

1. Create `prompts/<new_id>.yaml` following the schema above.  Use `|` for `content`.
2. Validate the YAML locally:
   ```bash
   python -c "import yaml; yaml.safe_load(open('prompts/<new_id>.yaml'))"
   ```
3. In your agent, replace the inline string with:
   ```python
   from ..prompt_loader import load_prompt_content   # from src/agents/
   # or
   from src.prompt_loader import load_prompt_content  # absolute

   MY_PROMPT = load_prompt_content("<new_id>")
   ```
4. Update the table in this README.

## How to edit an existing prompt

- Edit the `content:` block in the relevant `.yaml` file.
- No code changes needed — the loader picks up the new text automatically (next process start).
- Add a comment in the YAML with the date and reason for the change if helpful.

## YAML authoring rules

- Use **spaces only** — no tabs anywhere in YAML files.
- Use the literal-block scalar (`|`) for `content:` — never folded (`>`).
- Do **not** truncate prompt text.  The file is the single source of truth.
- Keep the `id` field in sync with the filename stem.
