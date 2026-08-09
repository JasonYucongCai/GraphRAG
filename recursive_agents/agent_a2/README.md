# agent_a2 — The FIRST Recursive Agent, Level 2

Built strictly per **IPP v0.2.8**. This is the **FIRST COMPILATION** of the
self-adaptive recursive agent chain. Agent a1 CREATES agent a2 through its
OWN tools — not through a bootstrap script.

## Situation

| | |
|:---|:---|
| **Agent** | `agent_a2` (level 2) |
| **Engine** | `agent_a2/agent_a2_engine/` — Copilot-level engine with hooks, prompt assembler, autopilot, summarizer |
| **Tools** | `agent_a2/agent_a2_tools/` — **74 tools** in 15 categories |
| **Built by** | The recursive compiler from engine/tools templates |
| **Architecture** | NOT weaker than `assets/copilot_agent_engine` + `assets/copilot_agent_tools` |

## Engine — `agent_a2_engine/`

| Component | File | Description |
|:---|:---|:---|
| AgentA1Engine | `engine.py` | Full agentic loop with LLM function calling |
| HookSystem | `hooks.py` | 8 lifecycle hooks (session, stop, tool, compaction) |
| PromptAssembler | `prompt_assembler.py` | Composable system prompt assembly |
| AutopilotController | `autopilot.py` | Task completion detection |
| ContextSummarizer | `summarizer.py` | Intelligent context compaction |

## Tools — `agent_a2_tools/` (74 tools)

| Category | Count | Key Tools |
|:---|:---|:---|
| agent_construction | 8 | agent_plan, agent_generate, agent_create, agent_evaluate, agent_test, agent_improve, agent_deploy, agent_status |
| file | 6 | read_file, write_file, replace_string, multi_replace_string, create_directory, list_directory |
| search | 4 | grep_search, file_search, search_nodes, find_references |
| terminal | 6 | run_in_terminal, get_terminal_output, send_to_terminal, kill_terminal, terminal_selection, terminal_last_command |
| memory | 5 | memory_read, memory_write, memory_list, memory_delete, memory_search |
| graph | 8 | get_local_graph, read_node, validate_graph, summarize_local, list_projects, project_info, register_node, link_nodes |
| ipp | 5 | ipp_construct, ipp_verify, ipp_audit, ipp_status_report, ipp_check_invariants |
| llm | 3 | llm_chat, llm_check, llm_provider_info |
| evaluation | 5 | check_tool_count, check_recursive_capability, evaluate_engine_comprehensiveness, run_agent_pipeline, collect_feedback |
| documentation | 4 | write_readme, write_system_prompt, generate_docs, read_docs |
| log | 5 | write_log, read_log, list_logs, write_feedback, read_feedback |
| web | 3 | web_search, fetch_webpage, download_arxiv |
| system | 5 | current_time, get_environment, check_python_version, list_installed_packages, get_system_info |
| powershell | 3 | start_agent_process, stop_agent_process, check_agent_status |
| code | 4 | validate_code, compile_check, run_code_snippet, generate_python_file |

## Creating agent_a2

Agent a1 creates a2 through its **OWN** tools:

```python
# Step 1: Plan
engine._tools_node.invoke("agent_plan", {"agent_id": "a2"})

# Step 2: Generate (REAL filesystem work — writes files to disk)
engine._tools_node.invoke("agent_generate", {"agent_id": "a2", "level": 2})

# Step 3: Create (Γ-construct + verify 17 invariants)
engine._tools_node.invoke("agent_create", {"agent_id": "a2", "level": 2})

# Step 4: Evaluate
engine._tools_node.invoke("agent_evaluate", {"agent_id": "a2"})

# Step 5: Test + Improve + Deploy
engine._tools_node.invoke("agent_test", {"agent_id": "a2"})
engine._tools_node.invoke("agent_improve", {"agent_id": "a2", "iterations": 3})
engine._tools_node.invoke("agent_deploy", {"agent_id": "a2", "level": 2})

# Step 6: Verify
engine._tools_node.invoke("agent_status", {})
```

## Verification Checklist (agent_a2 must pass ALL)

1. ✅ `check_tool_count` → >= 50 tools
2. ✅ `check_recursive_capability` → has all 8 construction tools
3. ✅ `evaluate_engine_comprehensiveness` → hooks, prompt, autopilot, summarizer
4. ✅ `ipp_verify` → ALL 17 invariants pass
5. ✅ `ipp_audit` → audit chains intact
6. ✅ README.md in agent/, engine/, tools/

## IPP v0.2.8 Compliance

- Every call flows through the guardrail envelope: ι_pre → π → Ω → ι_post → ρ → τ*
- Hash-chained audit on every channel
- ALL 17 invariants verified at construction
- Audit logs: `recursive_agents/graph_data/logs/IPP/<node>.<channel>.jsonl`
