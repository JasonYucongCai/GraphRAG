# agent_a3_tools — 74 tools in 15 categories

The comprehensive tool suite of agent_a3. These are the agent's **HANDS** —
with them it thinks, evaluates, and self-acts to build agent_a3.

NOT weaker than `assets/copilot_agent_tools`. Every tool follows the
four-phase lifecycle: resolve_input → validate → prepare → invoke.

## Tool Inventory (74 tools)

### Agent Construction (8)
| Tool | Description |
|:---|:---|
| `agent_plan` | THINK — deterministic construction plan |
| `agent_generate` | GENERATE — render templates → folders on disk |
| `agent_create` | CREATE — Γ-construct + verify 17 invariants |
| `agent_evaluate` | EVALUATE — invariants + audit + channels |
| `agent_test` | TEST — pipeline → latency probe → feedback |
| `agent_improve` | IMPROVE — test → patch → retest |
| `agent_deploy` | DEPLOY — generate + construct + register |
| `agent_status` | Report the constructed chain |

### File & Code (10)
`read_file`, `write_file`, `replace_string`, `multi_replace_string`,
`create_directory`, `list_directory`, `validate_code`, `compile_check`,
`run_code_snippet`, `generate_python_file`

### Search (4)
`grep_search`, `file_search`, `search_nodes`, `find_references`

### Terminal (6)
`run_in_terminal`, `get_terminal_output`, `send_to_terminal`,
`kill_terminal`, `terminal_selection`, `terminal_last_command`

### Memory (5)
`memory_read`, `memory_write`, `memory_list`, `memory_delete`, `memory_search`

### Graph (8)
`get_local_graph`, `read_node`, `validate_graph`, `summarize_local`,
`list_projects`, `project_info`, `register_node`, `link_nodes`

### IPP (5)
`ipp_construct`, `ipp_verify`, `ipp_audit`, `ipp_status_report`, `ipp_check_invariants`

### LLM (3)
`llm_chat`, `llm_check`, `llm_provider_info`

### Evaluation (5)
`check_tool_count`, `check_recursive_capability`, `evaluate_engine_comprehensiveness`,
`run_agent_pipeline`, `collect_feedback`

### Documentation (4)
`write_readme`, `write_system_prompt`, `generate_docs`, `read_docs`

### Logging (5)
`write_log`, `read_log`, `list_logs`, `write_feedback`, `read_feedback`

### Web (3)
`web_search`, `fetch_webpage`, `download_arxiv`

### System (5)
`current_time`, `get_environment`, `check_python_version`,
`list_installed_packages`, `get_system_info`

### PowerShell (3)
`start_agent_process`, `stop_agent_process`, `check_agent_status`

## IPP Compliance

- Every channel flows through the guardrail envelope: ι_pre → π → Ω → ι_post → ρ → τ*
- Hash-chained audit on every channel
- ALL 17 invariants verified at construction
- The tools ARE the implementation, the channels ARE the guardrail surface

## Files

- `tool_base.py` — BaseTool, ReadOnlyTool, EditTool, ExecuteTool, WebTool, MemoryTool
- `tool_registry.py` — AgentA1Toolkit (per-agent registry)
- `agent_construction_tools.py` — The 8 agent creation tools
- `file_tools.py` — File I/O tools (6)
- `search_tools.py` — Search tools (4)
- `terminal_tools.py` — Terminal tools (6)
- `memory_tools.py` — Memory tools (5)
- `graph_tools.py` — Graph tools (8)
- `ipp_tools.py` — IPP tools (5)
- `llm_tools.py` — LLM tools (3)
- `evaluation_tools.py` — Evaluation tools (5)
- `documentation_tools.py` — Documentation tools (4)
- `log_tools.py` — Logging tools (5)
- `web_tools.py` — Web tools (3)
- `system_tools.py` — System tools (5)
- `powershell_tools.py` — PowerShell tools (3)
- `code_tools.py` — Code tools (4)
- `IPP.json` — The F-file (node_id `agent_a3_tools`)
- `IPP_object.py` — The Ω handler factories
- `IPP_executor.py` — The Ξ class
