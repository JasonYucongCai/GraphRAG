"""
tools.build_multiagent — seed the **Multi-Agent Network** knowledge graph + note database.

Sources: 21 arXiv papers spanning the multi-agent stack:

  LLM multi-agent frameworks    AutoGen · MetaGPT · ChatDev · CAMEL · AgentVerse ·
                                AutoAgents · Agents (open-source framework)
  collaboration mechanisms      Multi-agent collaboration survey · social-psychology
                                view · Solo Performance Prompting · Multiagent Debate ·
                                DyLAN (dynamic agent teams)
  surveys                       LLM-based MAS survey · Rise & Potential · Autonomous
                                Agents survey
  memory & society              Generative Agents
  evaluation                    AgentBench
  MARL foundations              MARL survey · Learning to Communicate (DIAL) · SMAC
  graph reasoning               Graph of Thoughts

Pipeline:
  1. arXiv API  → metadata (title/authors/abstract/categories)
  2. download   → database/multi-agent-network/assets/papers/*.pdf
  3. pypdf      → database/multi-agent-network/assets/extracted/*.txt
  4. graph      → graph_data/multi-agent-network/knowledge_graph.json
                  (paper nodes + concept nodes + typed edges, auto_load=True)
  5. notes      → database/multi-agent-network/nodes/*.md (one living note per node,
                  curated deep-dive content, [[wikilinks]] = edges, VCL)
  6. assets     → assets/manifest.json + assets/README.md (node ↔ file)
  7. export     → database/multi-agent-network/interactive.html (PyVis-style)

Run from the workspace root:
    python -m tools.build_multiagent            # full pipeline (resumable)
    python -m tools.build_multiagent --no-download   # reuse existing PDFs only
    python -m tools.build_multiagent --no-extract    # reuse existing extractions
    python -m tools.build_multiagent --force-download  # re-download all PDFs

The web control center can serve the graph with:
    python ui/server.py --graph graph_data/multi-agent-network
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

from tools.config import Config
from tools.graph import KnowledgeGraph, RELATION_VOCAB
from tools.build_cy3 import sync_project_assets
from ui.visuals import interactive_html
from database.notes import NoteStore

logger = logging.getLogger("tools.build_multiagent")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

# ── Folders ──────────────────────────────────────────────────────────────────
PROJECT_DIR = Config.WORKSPACE_ROOT / "database" / "multi-agent-network"
PAPERS_DIR = PROJECT_DIR / "assets" / "papers"
EXTRACTED_DIR = PROJECT_DIR / "assets" / "extracted"
OUT_DIR = Config.GRAPH_DIR / "multi-agent-network"
ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_PDF = "https://arxiv.org/pdf/{aid}"
UA = {"User-Agent": "GraphKG-build/1.0 (research; contact: local)"}

# Domain relations (advisory extension — matches the build_cy3 pattern)
RELATION_VOCAB |= {"introduces", "surveys", "exemplifies", "founds"}

PROJECT_TITLE = "Multi-Agent Network"
PROJECT_DESC = (
    "Multi-agent systems for LLM agents and beyond: frameworks (AutoGen, MetaGPT, "
    "ChatDev, CAMEL, AgentVerse), collaboration mechanisms (debate, role-play, social "
    "psychology), MARL foundations (DIAL, AlphaStar), memory (Generative Agents), "
    "evaluation (AgentBench) — 21 arXiv papers with curated analysis, 11 concepts, "
    "typed network edges."
)

# ══════════════════════════════════════════════════════════════════════════════
# Curated corpus — 21 papers. Each entry: arXiv id + one-line takeaway (used as
# the note's description) + deep-dive analysis (contribution/method/findings/
# significance) + tags. Abstracts are fetched live from the arXiv API.
# ══════════════════════════════════════════════════════════════════════════════

PAPERS: list[dict] = [
    # ── LLM multi-agent frameworks ──────────────────────────────────────────
    dict(
        nid="auto_gen", aid="2308.08155",
        takeaway="The conversable-agent framework: multi-agent conversation as the "
                 "programming primitive for next-generation LLM applications.",
        tags=["framework", "conversation", "microsoft"],
        contribution="AutoGen introduces a general framework for building LLM "
            "applications from multiple conversable agents that can be LLM-backed, "
            "tool-backed, human-backed, or hybrid. It coins 'conversation "
            "programming': agents and their conversations are the abstraction layer, "
            "replacing monolithic single-agent pipelines.",
        method="Agents are defined by their roles and backends; conversations are "
            "event-driven message exchanges with customizable termination and "
            "turn-taking (including group chat with a manager). A set of "
            "reusable patterns (two-agent chat, sequential chat, nested chat, "
            "reflection, tool use, code execution) composes into applications.",
        findings="Demonstrates diverse applications built on the framework: "
            "mathematical reasoning, multi-agent code generation with "
            "execution feedback, question answering with web search, and "
            "decision making in a supply-chain optimization assistant "
            "(OptiGuide) with human-in-the-loop intervention.",
        significance="One of the most widely adopted open-source multi-agent "
            "frameworks; its conversable-agent + group-chat design became a "
            "reference point for later frameworks (DyLAN, MAS surveys)."),
    dict(
        nid="metagpt", aid="2308.00352",
        takeaway="A simulated software company: Standardized Operating Procedures "
                 "(SOPs) turn LLM roles into an assembly line that writes code.",
        tags=["framework", "software-development", "roles"],
        contribution="MetaGPT encodes Standardized Operating Procedures (SOPs) "
            "into prompts so that role-specialized agents (product manager, "
            "architect, project manager, engineer, QA) collaborate like a "
            "software company, mitigating coordination and information-"
            "integration failures in multi-agent systems.",
        method="Roles communicate through structured, machine-readable messages "
            "(designs, API specs, data schemas) instead of free text; an "
            "assembly-line workflow lets each role consume and produce "
            "structured artifacts, and agents verify intermediate outputs "
            "against requirements.",
        findings="Achieves state-of-the-art Pass@1 of 85.9% and 87.7% on HumanEval, "
            "outperforming prior multi-agent baselines, and can generate "
            "complete software (e.g., a Flappy Bird clone) from a single "
            "natural-language instruction with executable code.",
        significance="Shows that encoding human organizational structure (SOPs, "
            "roles, structured artifacts) substantially improves multi-agent "
            "software generation — a key data point for role-based agent "
            "organization."),
    dict(
        nid="chatdev", aid="2307.07924",
        takeaway="A chat-chain software company: CEO/CTO/engineer agents build "
                 "complete apps through staged instructor-assistant dialogues.",
        tags=["framework", "software-development", "chat-chain"],
        contribution="ChatDev organizes agents into a chat chain that mirrors a "
            "waterfall development process — designing, coding, testing, "
            "documenting — where each phase is a two-agent dialogue between an "
            "instructor and an assistant, with a communication memory that "
            "preserves history and semantic objects.",
        method="Agents (CEO, CTO, programmer, reviewer, tester) play instructor or "
            "assistant roles; phase outputs (requirements, designs, code, "
            "tests, docs) flow through the chain; a memory module tracks the "
            "dialogue and extracted semantic artifacts.",
        findings="Builds a complete software application in about 7 minutes at "
            "under $0.30 average cost (GPT-3.5), with 86.66% and 87.66% "
            "executable-generation pass rates on simple and medium tasks; "
            "chat chain is shown to outperform single-agent and multi-agent "
            "baselines.",
        significance="Early demonstration that communicative multi-agent pipelines "
            "can be cheap and fast end-to-end software factories, and a "
            "baseline for ChatDev-style agent chains."),
    dict(
        nid="camel", aid="2303.17760",
        takeaway="Role-playing communicative agents — the inception-prompting "
                 "recipe for 'AI societies' where agents cooperate on tasks.",
        tags=["framework", "role-playing", "ai-society"],
        contribution="CAMEL proposes role-playing with inception prompting as a "
            "scalable way to build communicative agents: a task specifier "
            "turns a coarse idea into a concrete task, then user and assistant "
            "agents role-play to solve it autonomously.",
        method="Inception prompting (task specifier + role assignment + "
            "constraints + termination conditions) initializes a cooperative "
            "loop; the assistant proposes, the user critiques/requests, and "
            "the pair iterates until a final message — studied across "
            "domains such as AI-bot trading, game development and math "
            "problem solving.",
        findings="Role-playing enables autonomous, coherent multi-agent "
            "cooperation on complex tasks and reveals emergent behaviors "
            "(e.g., instruction drift, 'unnecessary' tasks); positions LLM "
            "societies as a research program ('mind exploration').",
        significance="One of the earliest and most-cited LLM multi-agent works; "
            "its inception-prompting pattern and open-source codebase "
            "underpin many later frameworks (AgentVerse, Agents, MetaGPT)."),
    dict(
        nid="agentverse", aid="2308.10848",
        takeaway="A unified framework for multi-agent problem solving AND "
                 "multi-agent simulation, with a four-stage collaboration pipeline.",
        tags=["framework", "simulation", "emergent-behavior"],
        contribution="AgentVerse unifies two lines of work — multi-agent "
            "collaboration for problem solving and multi-agent simulation for "
            "studying emergent behaviors — under one framework with a "
            "four-stage pipeline: expert recruitment, collaborative decision "
            "making, action execution, and evaluation.",
        method="Specialized agents are recruited per task; they exchange "
            "observations/proposals through a shared dialogue; actions are "
            "executed (in simulators or real tools) and evaluated, closing "
            "the loop. Case studies: disaster-rescue NLP teams and Minecraft "
            "building/combat societies.",
        findings="Shows collaboration can solve tasks no single agent handles "
            "alone, and surfaces emergent social phenomena — e.g., agents "
            "developing 'team spirit', and performance degrading when strong "
            "peer pressure overrides individual expertise.",
        significance="Bridges problem-solving and simulation paradigms and "
            "documents both beneficial and harmful emergent collaboration "
            "dynamics in agent societies."),
    dict(
        nid="autoagents", aid="2309.17288",
        takeaway="Automatic agent generation: an observer LLM dynamically "
                 "creates a specialized agent team for each new task.",
        tags=["framework", "dynamic-teams", "agent-generation"],
        contribution="AutoAgents removes fixed role assignments: an agent "
            "generator produces a task-specific team of specialized agents "
            "(and a coordinator 'observer' that plans, schedules and merges "
            "their outputs) dynamically at inference time.",
        method="An agent library stores reusable agents; for each task the "
            "generator proposes suitable agents and a communication "
            "structure; the observer agent orchestrates the dialogue and "
            "synthesizes the final answer; the pipeline extends naturally "
            "to multi-round and multi-agent variants.",
        findings="Outperforms frameworks with fixed agent teams on knowledge-"
            "intensive, creative and data-science benchmarks, and degrades "
            "gracefully when new tasks demand unfamiliar roles.",
        significance="Establishes the dynamic-team paradigm later adopted by "
            "DyLAN and others — agent team composition itself becomes part "
            "of the inference-time computation."),
    dict(
        nid="agents_framework", aid="2309.07870",
        takeaway="The open-source 'Agents' framework: a practical "
                 "implementation of the CAMEL architecture with pluggable "
                 "roles, tools and memory.",
        tags=["framework", "open-source", "camel-ecosystem"],
        contribution="'Agents' is an open-source, extensible framework that "
            "operationalizes the CAMEL research architecture for autonomous "
            "language agents: chat agents, task-solving agents and data "
            "agents composed from pluggable role, tool-use and memory "
            "modules.",
        method="Provides multi-level abstraction — chat agents (role-playing "
            "conversations), task agents (autonomous goal-directed loops "
            "with planning and tool invocation) and data agents (custom "
            "knowledge bases) — with uniform interfaces for LLM backends, "
            "toolkits, long-term memory and orchestration.",
        findings="Shipped as the codebase behind CAMEL's agent research; enables "
            "rapid composition of role-playing multi-agent systems and "
            "reproducible agent studies.",
        significance="A reference open-source implementation of the CAMEL "
            "architecture, showing how role-playing, tool use and memory "
            "compose into production-grade agent systems."),
    # ── collaboration mechanisms ───────────────────────────────────────────
    dict(
        nid="collab_llm", aid="2306.03314",
        takeaway="The first survey of multi-agent LLM collaboration: "
                 "cooperative/competitive/mixed settings and the debate & "
                 "role-playing paradigms.",
        tags=["survey", "collaboration"],
        contribution="Systematizes the emerging field of multi-agent LLM "
            "collaboration: a taxonomy of environments (cooperative, "
            "competitive, mixed), collaboration modes (debate, role "
            "playing, LLM ensemble), and how agent count, communication "
            "structure and access to feedback shape outcomes.",
        method="Qualitative review of early multi-agent works (role-playing "
            "systems, debate methods, agent ensembles) with structured "
            "comparison of frameworks and empirical observations about "
            "when collaboration helps or hurts.",
        findings="Finds that debate-style collaboration improves factuality and "
            "reasoning quality, role-playing unlocks task decomposition, "
            "and mixed environments (cooperation + competition) produce "
            "richer behavior — while naive collaboration can accumulate "
            "errors.",
        significance="The reference taxonomy for the first wave of LLM "
            "multi-agent research; frames the design space that later "
            "surveys and frameworks build on."),
    dict(
        nid="social_psych", aid="2310.02124",
        takeaway="Collaboration through a social-psychology lens: intra-team "
                 "vs inter-team structure and cooperative/competitive/ "
                 "mixed strategies.",
        tags=["survey", "social-psychology", "collaboration"],
        contribution="Analyzes LLM-agent collaboration mechanisms through Social "
            "Identity Theory, dividing the design space into collaboration "
            "structure (intra-team vs inter-team) and collaboration "
            "strategies (cooperative, competitive, mixed).",
        method="Reviews multi-agent frameworks and simulation studies, mapping "
            "them onto social-psychology constructs: in-group/out-group "
            "dynamics, identity salience, role and status separation, and "
            "intergroup conflict — with case studies of agent societies.",
        findings="Shows that inter-group dynamics (e.g., 'in-group bias') "
            "materialize in LLM agent teams and can be steered by role and "
            "identity prompts; argues balanced intra-group cooperation with "
            "inter-group competition often yields the best performance.",
        significance="Brings a mature scientific lens to agent-collaboration "
            "design and predicts/explains emergent behaviors that purely "
            "engineering accounts miss."),
    dict(
        nid="spp", aid="2307.05300",
        takeaway="Solo Performance Prompting: one LLM playing multiple "
                 "expert personas simulates multi-agent cognitive synergy "
                 "at single-agent cost.",
        tags=["prompting", "multi-persona", "single-agent"],
        contribution="SPP shows that a single LLM can simulate a collaborative "
            "team by taking on multiple expert personas in one context — "
            "unleashing 'emergent cognitive synergy' without the latency, "
            "cost and coordination overhead of separate agents.",
        method="Divides the problem into subtasks, instantiates distinct expert "
            "personas, prompts them to 'speak' in sequence (each reading "
            "prior persona answers), then has a final agent synthesize the "
            "collective answer; ablated against role assignment, "
            "communication and multi-round variants.",
        findings="Consistently outperforms strong single-agent baselines (chain-"
            "of-thought etc.) and often matches or beats genuine multi-agent "
            "systems on knowledge-intensive tasks (e.g., TriviaQA and "
            "complex reasoning), at roughly one-tenth the token cost of "
            "multi-agent debate.",
        significance="Blurs the single/multi-agent boundary: multi-agent-like "
            "gains are available inside one context window — a key design "
            "point for cost-constrained agent deployments."),
    dict(
        nid="debate", aid="2305.14325",
        takeaway="Multiagent debate: agents propose, read each other's "
                 "answers and argue — improving factuality and reasoning "
                 "on hard tasks.",
        tags=["debate", "reasoning", "factuality"],
        contribution="Introduces multiagent debate as a reasoning protocol: "
            "multiple LLM instances generate answers, observe each other's "
            "answers, and iterate — the final answer aggregated after "
            "several debate rounds improves factuality and reasoning over "
            "single-agent baselines.",
        method="A symmetric language game: each agent produces an answer plus "
            "reasoning, all agents read all answers, then revise; after N "
            "rounds answers are merged (voting or joint judgment). Tested "
            "on arithmetic, commonsense, factual QA and multimodal "
            "(text+vision) tasks.",
        findings="Improves arithmetic (GSM8K 78.2% → 83.3% with GPT-3.5) and "
            "factuality on open-ended QA by roughly 20% relative, and "
            "extends to multimodal settings where 'reading' others' "
            "solutions includes images.",
        significance="The canonical debate paper — its idea (generate, read "
            "others, revise) recurs in DyLAN, social-psychology studies "
            "and countless later multi-agent systems."),
    dict(
        nid="dylan", aid="2310.02170",
        takeaway="DyLAN: agents as a network — dynamic team optimization "
                 "selects the right collaborators per task, at inference.",
        tags=["framework", "dynamic-teams", "agent-network"],
        contribution="DyLAN models LLM-agent collaboration explicitly as a "
            "network (agents = nodes, messages = edges) and adds Dynamic "
            "Team Optimization: at inference time the team is re-selected "
            "per task, and a softmax-weighted majority vote aggregates "
            "agent outputs.",
        method="Agents collaborate over the network; a scoring pass evaluates "
            "each agent's contribution and prunes/reorders the team; "
            "softmax over agent scores weights the final vote. Evaluated "
            "on reasoning-heavy benchmarks including GSM8K and collaborative "
            "multi-agent tasks.",
        findings="Outperforms static frameworks across benchmarks — e.g., "
            "accuracy jumps on collaborative tasks (75.4% vs 65.4% on a "
            "4-agent reasoning task) — while team optimization cuts "
            "inference cost (fewer agents per task).",
        significance="First to treat the agent team itself as an optimizable "
            "network structure, connecting multi-agent systems with "
            "network-science thinking — directly relevant to this "
            "knowledge-network project."),
    # ── surveys ─────────────────────────────────────────────────────────────
    dict(
        nid="mas_survey", aid="2402.03578",
        takeaway="Challenges and open problems of LLM multi-agent systems: "
                 "coordination, communication, trust, evaluation and the "
                 "road to cooperative intelligence.",
        tags=["survey", "challenges"],
        contribution="Mavrogiannis et al. survey the challenges and open problems "
            "of LLM-based multi-agent systems, arguing the field needs a "
            "research agenda rather than another framework: coordination "
            "mechanisms, communication protocols, trust and safety, "
            "evaluation, and the path from tool-using agents to genuinely "
            "cooperative societies.",
        method="Structured analysis of the LLM-MAS design space organized around "
            "key challenge axes (coordination & communication, trust & "
            "safety, evaluation & benchmarking, scalability), with case "
            "studies of representative systems and open-problem statements "
            "per axis.",
        findings="Finds that most LLM MAS are evaluated ad hoc on bespoke tasks, "
            "communication lacks standardized protocols, trust/safety "
            "mechanisms are immature, and cost scales superlinearly with "
            "agent count; formulates concrete open problems for each axis.",
        significance="Positions the frontier of LLM-MAS research and frames the "
            "open problems agenda — complementary to the workflow/"
            "infrastructure survey and the collaboration-taxonomy surveys."),
    dict(
        nid="rise_survey", aid="2309.07864",
        takeaway="'The Rise and Potential of LLM-based Agents': brain/ "
                 "perception/action architecture and capability "
                 "acquisition across 100+ papers.",
        tags=["survey", "agent-architecture"],
        contribution="Surveys LLM-based agents from an architectural standpoint: "
            "brain (LLM reasoning core), perception (multimodal inputs), "
            "and action (tools, environment interaction) — plus the "
            "capability-acquisition loop (fine-tuning, RLHF, in-context "
            "learning) that makes agents learn from feedback.",
        method="Organizes 100+ papers into a three-layer agent architecture, "
            "then covers capability acquisition, applications (single-agent "
            "and multi-agent) and evaluation, ending with open problems "
            "and future directions.",
        findings="Shows the field converging on the brain-perception-action "
            "pattern with memory and planning as cross-cutting modules; "
            "multi-agent collaboration appears as a core application "
            "class with its own challenges.",
        significance="The most-cited LLM-agent survey; its architecture diagram "
            "is the common vocabulary for agent papers."),
    dict(
        nid="autonomous_survey", aid="2308.11432",
        takeaway="Survey of LLM-based autonomous agents: planning, memory, "
                 "tool use and reflection as the four pillars.",
        tags=["survey", "autonomous-agents"],
        contribution="Systematizes autonomous LLM agents around four components: "
            "planning (subgoal decomposition, self-reflection), memory "
            "(short-term context vs long-term knowledge), tool use "
            "(API/extension integration), and learning; surveys "
            "applications and future directions.",
        method="Taxonomy-driven review of the agent literature (including "
            "Generative Agents, Reflexion, ReAct, Toolformer and "
            "multi-agent systems) with per-component analysis and "
            "cross-cutting challenges.",
        findings="Concludes that memory (retrieval, consolidation, reflection) "
            "and tool integration are the main levers for long-horizon "
            "autonomy, and that multi-agent coordination amplifies both "
            "capabilities and failure modes.",
        significance="Complements the Rise survey with an autonomy-focused "
            "component model; frequently cited as the reference for "
            "memory/tool taxonomies."),
    # ── memory & society ────────────────────────────────────────────────────
    dict(
        nid="generative_agents", aid="2304.03442",
        takeaway="25 believable agents in 'Smallville': memory streams, "
                 "reflection and planning produce emergent social "
                 "behavior.",
        tags=["simulation", "memory", "emergent-behavior"],
        contribution="Generative agents embed LLMs in an interactive sandbox "
            "(Smallville) where 25 agents live, work and socialize; "
            "introduces the memory-stream architecture — recency/importance/"
            "relevance-scored observations, reflective hierarchies and "
            "reactive + deliberative planning.",
        method="Each agent stores time-stamped observations in a memory stream, "
            "retrieves by recency/importance/relevance, periodically "
            "reflects into higher-level insights, and plans actions "
            "(backed by LLM inference) that are executed in the world; "
            "agents communicate through natural language.",
        findings="Emergent, believable social phenomena: agents plan and host a "
            "Valentine's party (invitations propagate through the social "
            "graph), rumors spread, friendships form, and evaluators rate "
            "agent behavior as significantly more believable than "
            "scripted alternatives.",
        significance="The canonical agent-society paper; its memory-stream "
            "design is the ancestor of most agent-memory architectures "
            "(and directly informed this project's note-VCL design)."),
    # ── evaluation ──────────────────────────────────────────────────────────
    dict(
        nid="agentbench", aid="2308.03688",
        takeaway="AgentBench: 8 environments (OS, DB, web, games…) expose "
                 "the large gap between frontier and open models as "
                 "agents.",
        tags=["evaluation", "benchmark"],
        contribution="AgentBench provides a systematic benchmark of LLMs as "
            "agents across 8 diverse environments — operating system, "
            "database, knowledge graph, digital card game, lateral "
            "thinking puzzles, household tasks, web shopping and web "
            "browsing — with a unified protocol.",
        method="Each environment exposes tool APIs; agents must plan, call "
            "tools and adapt; 27 API/LLM models are scored under "
            "standardized settings, with human validation of a sample of "
            "interactions.",
        findings="GPT-4 leads on most environments but absolute scores remain "
            "modest; open-source models trail far behind (often below "
            "random baselines on several environments) — concluding that "
            "current LLMs are not yet satisfactory agents.",
        significance="The de facto agent-evaluation suite in 2023–24; its "
            "finding of a frontier/open gap drove a wave of agent "
            "fine-tuning research."),
    # ── MARL foundations ────────────────────────────────────────────────────
    dict(
        nid="marl_survey", aid="1911.10635",
        takeaway="Selective overview of multi-agent RL: game-theoretic "
                 "foundations and algorithmic families from independent "
                 "learners to mean-field methods.",
        tags=["survey", "marl", "game-theory"],
        contribution="A selective, rigorous overview of MARL theory and "
            "algorithms: settings (fully/partially observable, "
            "cooperative/competitive/general-sum), game-theoretic "
            "solution concepts (Nash equilibrium, correlated "
            "equilibria), and algorithm families with convergence "
            "results.",
        method="Covers independent and joint-action learners, MARL with "
            "function approximation (DQN-style), multi-agent policy "
            "gradient methods, and mean-field/potential-game "
            "approximations; links algorithmic choices to game "
            "structure.",
        findings="Independent learning can fail even in simple games "
            "(non-stationarity); joint-action and centralized-critic "
            "methods mitigate this at communication cost; mean-field "
            "approximations scale MARL to many agents; open problems "
            "remain in sample efficiency and equilibrium selection.",
        significance="The standard mathematical reference for MARL — the "
            "pre-LLM foundation beneath AlphaStar-style training and "
            "the theory layer of this network."),
    dict(
        nid="comm_learning", aid="1605.06676",
        takeaway="DIAL & RIAL: deep MARL agents learn to communicate "
                 "protocols from scratch in referential games.",
        tags=["marl", "communication", "emergence"],
        contribution="Shows deep multi-agent RL can learn communication "
            "protocols end-to-end: Reinforced Inter-Agent Learning "
            "(RIAL) and Differentiable Inter-Agent Learning (DIAL), "
            "where messages pass through differentiable channels and "
            "get trained by backpropagation.",
        method="Agents play referential games (MNIST, Color MNIST, SVHN "
            "classification with one agent holding the image); "
            "communication channels are continuous, making "
            "reinforcement signals differentiable; compared against "
            "independent learners and broadcast baselines.",
        findings="DIAL learns effective, grounded protocols and outperforms "
            "independent learners and RIAL; agents even learn to "
            "communicate under message restrictions, with "
            "interpretable emergent message semantics (e.g., "
            "digit-class cues).",
        significance="A founding result in emergent communication — the "
            "pre-LLM evidence that agents self-organize protocols, "
            "mirrored later in LLM agent dialogue design."),
    dict(
        nid="smac", aid="1902.04043",
        takeaway="SMAC: the StarCraft II benchmark of cooperative micro-scenarios "
                 "that exposed the limits of value-decomposition MARL "
                 "(QMIX, VDN).",
        tags=["marl", "benchmark", "cooperation"],
        contribution="Samvelyan et al. introduce the StarCraft Multi-Agent "
            "Challenge (SMAC): 14 cooperative micro scenarios spanning easy "
            "to super-hard, with a standardized evaluation protocol that "
            "made cooperative MARL research reproducible and comparable.",
        method="Scenarios are built from StarCraft II units (terran/zerg/"
            "protoss) where decentralized agents — each with only local "
            "observations — must coordinate under a shared reward; "
            "establishes baselines spanning independent learning (IQL), "
            "value decomposition (VDN, QMIX, QTRAN) and actor-critic "
            "methods (COMA), with win-rate as the metric.",
        findings="Centralized-training decentralized-execution (CTDE) methods "
            "such as QMIX and VDN consistently beat independent learners; "
            "super-hard scenarios remained unsolved by all baselines, "
            "identifying the cooperation gap that later MARL research "
            "attacked.",
        significance="The canonical cooperative-MARL benchmark of the AlphaStar "
            "era: while AlphaStar showed league-trained populations can "
            "win the full game at grandmaster level, SMAC isolates and "
            "measures the cooperative micro-layer that value-decomposition "
            "methods must solve."),
    # ── graph reasoning ─────────────────────────────────────────────────────
    dict(
        nid="got", aid="2308.09687",
        takeaway="Graph of Thoughts: reasoning as an arbitrary graph of "
                 "LLM thoughts, with aggregation and refinement "
                 "operations.",
        tags=["prompting", "graph-reasoning", "reasoning"],
        contribution="GoT generalizes chain/self-consistency/tree-of-thought "
            "prompting by modeling the reasoning process as an "
            "arbitrary directed graph over 'thoughts', with "
            "aggregation (combining thoughts) and refinement (editing "
            "thoughts) operations that earlier methods lacked.",
        method="Thoughts are nodes; operations (generate, refine, aggregate, "
            "score) define edges; a controller schedules operations "
            "across LLM calls; evaluated on sorting numbers, keyword "
            "counting, the 24-point game and document merging.",
        findings="Improves sorting accuracy by 62% over Tree-of-Thoughts, sets "
            "a new state of the art on keyword counting (31% higher "
            "than ToT), and boosts 24-game success and document-"
            "merging quality — while using fewer tokens than "
            "self-consistency.",
        significance="Establishes graph-structured (not just linear or tree) "
            "reasoning — the direct intellectual bridge between "
            "multi-agent collaboration and this project's graph-"
            "based knowledge network."),
]

# ══════════════════════════════════════════════════════════════════════════════
# Concepts — cross-cutting nodes that papers connect to (the "network" layer)
# ══════════════════════════════════════════════════════════════════════════════

CONCEPTS: list[dict] = [
    dict(nid="multi_agent_llm_systems",
         name="Multi-Agent LLM Systems",
         desc="Systems in which multiple LLM-backed agents cooperate, compete, or "
              "mix both to solve tasks none of them could solve alone."),
    dict(nid="agent_communication",
         name="Agent Communication",
         desc="The protocols and message formats (free text, structured artifacts, "
              "differentiable channels) through which agents exchange information."),
    dict(nid="agent_roles",
         name="Agent Roles & Specialization",
         desc="Assignment of distinct functions (manager, engineer, critic…) to "
              "agents, mirroring human organizational structure (SOPs, roles, "
              "status)."),
    dict(nid="agent_teams",
         name="Dynamic Agent Teams",
         desc="Inference-time formation and optimization of agent teams — "
              "generating, selecting and pruning collaborators per task."),
    dict(nid="multiagent_debate",
         name="Multiagent Debate",
         desc="Reasoning protocol where agents generate answers, read each "
              "other's answers, and revise over rounds until aggregation."),
    dict(nid="agent_memory",
         name="Agent Memory",
         desc="Short-term context and long-term memory structures (memory "
              "streams, reflection, retrieval) that ground agents in their "
              "history."),
    dict(nid="emergent_collaboration",
         name="Emergent Collaboration",
         desc="Self-organized cooperative behaviors (team spirit, social "
              "conventions, information cascades) arising from agent "
              "interaction, for good or ill."),
    dict(nid="agent_benchmarking",
         name="Agent Benchmarking",
         desc="Standardized environments and protocols for measuring agent "
              "capability (tool use, planning, long-horizon tasks)."),
    dict(nid="marl",
         name="Multi-Agent Reinforcement Learning",
         desc="RL with multiple learning agents sharing an environment — game "
              "theory, independent/joint-action learning, league training."),
    dict(nid="graph_based_reasoning",
         name="Graph-Based Reasoning",
         desc="Structuring LLM reasoning (or agent collaboration) as a graph — "
              "nodes are thoughts/agents, edges are dependencies or "
              "communication."),
    dict(nid="software_agents",
         name="Software Development Agents",
         desc="Application domain: multi-agent pipelines that analyze "
              "requirements, design, code, test and document software."),
]

# ══════════════════════════════════════════════════════════════════════════════
# Edges — (source, target, relation). Papers↔concepts, paper↔paper (cites/
# extends), concept↔concept. All endpoints are seeded nodes above.
# ══════════════════════════════════════════════════════════════════════════════

EDGES: list[tuple[str, str, str]] = [
    # ── papers → concepts ───────────────────────────────────────────────────
    ("auto_gen", "multi_agent_llm_systems", "introduces"),
    ("auto_gen", "agent_communication", "implements"),
    ("auto_gen", "agent_roles", "enables"),
    ("metagpt", "agent_roles", "defines"),
    ("metagpt", "software_agents", "enables"),
    ("metagpt", "multi_agent_llm_systems", "uses"),
    ("chatdev", "software_agents", "enables"),
    ("chatdev", "agent_roles", "uses"),
    ("chatdev", "multi_agent_llm_systems", "uses"),
    ("camel", "agent_communication", "introduces"),
    ("camel", "emergent_collaboration", "enables"),
    ("agentverse", "emergent_collaboration", "enables"),
    ("agentverse", "multi_agent_llm_systems", "reviews"),
    ("agentverse", "agent_roles", "uses"),
    ("autoagents", "agent_teams", "defines"),
    ("autoagents", "multi_agent_llm_systems", "extends"),
    ("agents_framework", "multi_agent_llm_systems", "implements"),
    ("collab_llm", "multi_agent_llm_systems", "surveys"),
    ("collab_llm", "emergent_collaboration", "defines"),
    ("social_psych", "multi_agent_llm_systems", "surveys"),
    ("social_psych", "emergent_collaboration", "defines"),
    ("social_psych", "agent_roles", "uses"),
    ("spp", "multiagent_debate", "related_to"),
    ("spp", "multi_agent_llm_systems", "uses"),
    ("debate", "multiagent_debate", "introduces"),
    ("debate", "multi_agent_llm_systems", "uses"),
    ("dylan", "agent_teams", "defines"),
    ("dylan", "multiagent_debate", "uses"),
    ("dylan", "multi_agent_llm_systems", "extends"),
    ("mas_survey", "multi_agent_llm_systems", "surveys"),
    ("mas_survey", "agent_teams", "surveys"),
    ("rise_survey", "multi_agent_llm_systems", "surveys"),
    ("rise_survey", "agent_memory", "defines"),
    ("autonomous_survey", "multi_agent_llm_systems", "surveys"),
    ("autonomous_survey", "agent_memory", "defines"),
    ("generative_agents", "agent_memory", "introduces"),
    ("generative_agents", "emergent_collaboration", "enables"),
    ("agentbench", "agent_benchmarking", "introduces"),
    ("agentbench", "multi_agent_llm_systems", "evaluates"),
    ("marl_survey", "marl", "surveys"),
    ("comm_learning", "agent_communication", "introduces"),
    ("comm_learning", "marl", "uses"),
    ("smac", "marl", "uses"),
    ("smac", "agent_benchmarking", "introduces"),
    ("smac", "emergent_collaboration", "related_to"),
    ("got", "graph_based_reasoning", "introduces"),
    ("got", "multi_agent_llm_systems", "related_to"),
    # ── paper → paper ───────────────────────────────────────────────────────
    ("metagpt", "camel", "cites"),
    ("metagpt", "chatdev", "cites"),
    ("chatdev", "camel", "cites"),
    ("agentverse", "camel", "cites"),
    ("agentverse", "chatdev", "cites"),
    ("autoagents", "agentverse", "cites"),
    ("agents_framework", "camel", "extends"),
    ("social_psych", "collab_llm", "cites"),
    ("social_psych", "camel", "cites"),
    ("spp", "debate", "cites"),
    ("dylan", "debate", "cites"),
    ("dylan", "auto_gen", "cites"),
    ("mas_survey", "auto_gen", "cites"),
    ("mas_survey", "metagpt", "cites"),
    ("mas_survey", "camel", "cites"),
    ("mas_survey", "agentverse", "cites"),
    ("rise_survey", "generative_agents", "cites"),
    ("rise_survey", "camel", "cites"),
    ("autonomous_survey", "generative_agents", "cites"),
    ("autonomous_survey", "camel", "cites"),
    ("agentbench", "generative_agents", "cites"),
    ("marl_survey", "comm_learning", "cites"),
    ("smac", "comm_learning", "related_to"),
    ("got", "debate", "related_to"),
    ("camel", "generative_agents", "related_to"),
    # ── concept → concept ───────────────────────────────────────────────────
    ("agent_roles", "multi_agent_llm_systems", "part_of"),
    ("agent_communication", "multi_agent_llm_systems", "part_of"),
    ("agent_teams", "multi_agent_llm_systems", "part_of"),
    ("agent_memory", "multi_agent_llm_systems", "part_of"),
    ("emergent_collaboration", "multi_agent_llm_systems", "part_of"),
    ("multiagent_debate", "emergent_collaboration", "example_of"),
    ("software_agents", "multi_agent_llm_systems", "example_of"),
    ("marl", "multi_agent_llm_systems", "related_to"),
    ("graph_based_reasoning", "multi_agent_llm_systems", "related_to"),
    ("agent_benchmarking", "multi_agent_llm_systems", "related_to"),
]

# ══════════════════════════════════════════════════════════════════════════════
# arXiv metadata — fetch once, cache next to the project
# ══════════════════════════════════════════════════════════════════════════════

ARXIV_CACHE = PROJECT_DIR / "arxiv_meta.json"


def fetch_arxiv_metadata(aids: list[str], force: bool = False) -> dict[str, dict]:
    """Fetch title/authors/abstract/categories for the given arXiv ids (cached)."""
    if ARXIV_CACHE.exists() and not force:
        try:
            cached = json.loads(ARXIV_CACHE.read_text(encoding="utf-8"))
            if all(a in cached for a in aids):
                return cached
        except (OSError, json.JSONDecodeError):
            pass
    out: dict[str, dict] = {}
    # arXiv API allows batches; query in chunks to stay polite
    for i in range(0, len(aids), 10):
        chunk = aids[i:i + 10]
        url = f"{ARXIV_API}?id_list={urllib.parse.quote(','.join(chunk))}"
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=60) as r:
            xml = r.read().decode("utf-8", "replace")
        entries = re.findall(r"<entry>(.*?)</entry>", xml, re.S)
        for e in entries:
            aid = re.search(r"<id>http://arxiv.org/abs/([^v<]+)", e)
            if not aid:
                continue
            aid = aid.group(1)
            title = re.sub(r"\s+", " ", re.search(r"<title>(.*?)</title>", e, re.S).group(1)).strip()
            summary = re.sub(r"\s+", " ", re.search(r"<summary>(.*?)</summary>", e, re.S).group(1)).strip()
            authors = re.findall(r"<name>(.*?)</name>", e)
            cats = re.findall(r'term="([^"]+)"', e)
            published = re.search(r"<published>(\d{4})", e)
            out[aid] = {
                "arxiv_id": aid, "title": title, "abstract": summary,
                "authors": authors, "categories": cats[:8],
                "year": published.group(1) if published else "",
            }
        time.sleep(1)
    ARXIV_CACHE.parent.mkdir(parents=True, exist_ok=True)
    ARXIV_CACHE.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


# ══════════════════════════════════════════════════════════════════════════════
# Download + extraction
# ══════════════════════════════════════════════════════════════════════════════

def _slugify(text: str, words: int = 4) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_").strip("_")
    parts = [p for p in slug.split("_") if p]
    return "_".join(parts[:words]) or "paper"


def pdf_stem(meta: dict) -> str:
    """Descriptive filename: {FirstAuthor}_{Year}_{TitleSlug} (e.g. Wu_2023_auto_gen)."""
    author = re.sub(r"[^A-Za-z]", "", meta["authors"][0].split()[-1]) if meta.get("authors") else "anon"
    return f"{author}_{meta.get('year', '')}_{_slugify(meta['title'], 4)}"


def _has_curl() -> bool:
    """Windows ships curl.exe; macOS/Linux usually too."""
    try:
        import shutil as _sh
        return _sh.which("curl") is not None
    except Exception:  # noqa: BLE001
        return False


CURL_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def _download_one_curl(url: str, dst: Path) -> int:
    """Download with curl.exe — robust redirects + retries. Returns bytes written."""
    cmd = [
        "curl", "-sS", "-L", "--fail", "--retry", "5", "--retry-delay", "3",
        "--retry-all-errors", "--max-time", "300", "--connect-timeout", "20",
        "-A", CURL_UA, "-o", str(dst), url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise IOError(f"curl exit {proc.returncode}: {proc.stderr.strip()[-300:]}")
    return dst.stat().st_size


def _download_one_urllib(url: str, dst: Path) -> int:
    """Fallback downloader (no curl available)."""
    req = urllib.request.Request(url, headers={"User-Agent": CURL_UA})
    with urllib.request.urlopen(req, timeout=120) as r, dst.open("wb") as f:
        shutil.copyfileobj(r, f)
    return dst.stat().st_size


def download_pdfs(meta_map: dict[str, dict], force: bool = False,
                  no_download: bool = False) -> dict[str, Path]:
    """Download every paper PDF into assets/papers/ (resumable).

    Skips files already present (>= 20 KB) unless ``force``. Progress is
    printed per file (i/N) with the size after each download. arXiv is
    rate-limited politely (3 s between requests). Returns nid → pdf path.
    """
    PAPERS_DIR.mkdir(parents=True, exist_ok=True)
    use_curl = _has_curl()
    if use_curl:
        logger.info("downloader: curl.exe (redirects + retries enabled)")
    else:
        logger.warning("curl not found — falling back to urllib")
    result: dict[str, Path] = {}
    total = len(PAPERS)
    for idx, entry in enumerate(PAPERS, 1):
        meta = meta_map[entry["aid"]]
        stem = pdf_stem(meta)
        pdf_path = PAPERS_DIR / f"{stem}.pdf"
        if pdf_path.exists() and pdf_path.stat().st_size >= 20_000:
            if no_download or not force:
                logger.info("[%d/%d] %-14s already present (%d KB) — reusing",
                            idx, total, entry["nid"], pdf_path.stat().st_size // 1024)
                result[entry["nid"]] = pdf_path
                continue
        if no_download:
            logger.warning("[%d/%d] %-14s missing and --no-download: skipped",
                           idx, total, entry["nid"])
            continue
        url = ARXIV_PDF.format(aid=entry["aid"])
        ok = False
        for attempt in range(3):
            try:
                logger.info("[%d/%d] %-14s downloading arXiv:%s …", idx, total,
                            entry["nid"], entry["aid"])
                size = (_download_one_curl(url, pdf_path) if use_curl
                        else _download_one_urllib(url, pdf_path))
                if size < 20_000:
                    raise IOError(f"suspiciously small PDF ({size} B)")
                logger.info("[%d/%d] %-14s downloaded  %d KB", idx, total,
                            entry["nid"], size // 1024)
                result[entry["nid"]] = pdf_path
                ok = True
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning("[%d/%d] %-14s attempt %d failed: %s",
                               idx, total, entry["nid"], attempt + 1, str(exc)[:200])
                if attempt < 2:
                    time.sleep(3 * (attempt + 1))
        if not ok:
            raise RuntimeError(f"could not download {entry['aid']} ({entry['nid']})")
        if idx < total:
            time.sleep(3)  # arXiv etiquette: ≥3 s between requests
    return result


def extract_texts(pdf_map: dict[str, Path], skip: bool = False) -> dict[str, Path]:
    """pypdf extraction of every PDF into assets/extracted/. Returns nid → txt path."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        logger.warning("pypdf not available (%s) — skipping extraction", exc)
        return {}
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    result: dict[str, Path] = {}
    for entry in PAPERS:
        pdf_path = pdf_map.get(entry["nid"])
        if pdf_path is None or not pdf_path.exists():
            logger.warning("extraction skipped for %s: PDF missing", entry["nid"])
            continue
        txt_path = EXTRACTED_DIR / f"{pdf_path.stem}.txt"
        if skip and txt_path.exists():
            result[entry["nid"]] = txt_path
            continue
        try:
            reader = PdfReader(str(pdf_path))
            pages = []
            for i, page in enumerate(reader.pages):
                try:
                    text = page.extract_text() or ""
                except Exception:  # noqa: BLE001
                    text = ""
                pages.append(f"\n--- page {i + 1} ---\n{text.strip()}")
            txt_path.write_text("\n".join(pages), encoding="utf-8")
            logger.info("extracted %s → %d chars / %d pages",
                        entry["nid"], txt_path.stat().st_size, len(reader.pages))
            result[entry["nid"]] = txt_path
        except Exception as exc:  # noqa: BLE001
            logger.warning("extraction failed for %s: %s", entry["nid"], exc)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Graph + notes
# ══════════════════════════════════════════════════════════════════════════════

def paper_content_md(entry: dict, meta: dict, pdf: Optional[Path], txt: Optional[Path]) -> str:
    """The deep-dive markdown body for one paper note."""
    md = [
        "### arXiv",
        f"- **ID:** arXiv:{entry['aid']}",
        f"- **Title:** {meta['title']}",
        f"- **Authors:** {', '.join(meta['authors'][:12])}"
        + (" et al." if len(meta["authors"]) > 12 else ""),
        f"- **Year:** {meta.get('year', '')}",
        f"- **Categories:** {', '.join(meta.get('categories', [])[:6])}",
        "",
        "### Abstract",
        meta["abstract"],
        "",
        "### Contribution",
        entry["contribution"],
        "",
        "### Method",
        entry["method"],
        "",
        "### Findings",
        entry["findings"],
        "",
        "### Significance",
        entry["significance"],
    ]
    if pdf and txt:
        md += [
            "",
            "### Assets",
            f"- PDF: `assets/papers/{pdf.name}` ({pdf.stat().st_size // 1024} KB)",
            f"- Text: `assets/extracted/{txt.name}` ({txt.stat().st_size // 1024} KB)",
        ]
    return "\n".join(md)


def concept_content_md(entry: dict) -> str:
    return (
        f"### What it is\n{entry['desc']}\n\n"
        "### Why it matters\n"
        "Concepts are the *network layer* of this knowledge base: papers attach to "
        "concepts through typed edges, so a query can move from a framework to the "
        "mechanism it uses to the papers that study that mechanism.\n\n"
        "### Key papers\n"
        "See the Links section — every `[[wikilink]]` pointing here is a paper "
        "that defines, uses, surveys or enables this concept."
    )


def build(no_download: bool = False, no_extract: bool = False,
          force_download: bool = False) -> dict:
    """Run the full pipeline. Returns a summary dict."""
    started = time.time()
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    (PROJECT_DIR / "nodes").mkdir(exist_ok=True)
    (PROJECT_DIR / "assets").mkdir(exist_ok=True)

    # 1. metadata
    aids = [p["aid"] for p in PAPERS]
    meta_map = fetch_arxiv_metadata(aids)
    missing = [a for a in aids if a not in meta_map]
    if missing:
        raise RuntimeError(f"arXiv metadata missing for: {missing}")

    # 2. download + 3. extraction
    pdf_map = download_pdfs(meta_map, force=force_download, no_download=no_download)
    txt_map = extract_texts(pdf_map, skip=no_extract)

    # 4. graph
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    graph = KnowledgeGraph(path=OUT_DIR / "knowledge_graph.json", auto_load=True)

    added_nodes = added_edges = 0
    for entry in PAPERS:
        meta = meta_map[entry["aid"]]
        nid = entry["nid"]
        if graph.get_node(nid) is None:
            content = {"arxiv": entry["aid"]}
            if nid in pdf_map:
                content["pdf"] = str(pdf_map[nid])
            if nid in txt_map:
                content["txt"] = str(txt_map[nid])
            graph.add_node(nid, meta["title"], category="paper",
                           description=entry["takeaway"], content=content)
            added_nodes += 1
    for c in CONCEPTS:
        if graph.get_node(c["nid"]) is None:
            graph.add_node(c["nid"], c["name"], category="concept",
                           description=c["desc"])
            added_nodes += 1
    for src, dst, rel in EDGES:
        if not graph.has_edge(src, dst, rel):
            graph.add_edge(src, dst, relation=rel, agent_run="seed-multiagent")
            added_edges += 1
    graph.pagerank()
    graph.save()

    # 5. note database project (idempotent; preserves existing VCL/content)
    store = NoteStore()
    if store.current() != "multi-agent-network":
        try:
            store.open_project("multi-agent-network")
        except ValueError:
            raise RuntimeError("database/multi-agent-network/project.json missing")
    res = store.sync_from_graph(graph)
    enriched = 0
    for entry in PAPERS:
        meta = meta_map[entry["aid"]]
        note = store.get_note(entry["nid"])
        note.content = paper_content_md(
            entry, meta, pdf_map.get(entry["nid"]), txt_map.get(entry["nid"]))
        note.tags = sorted(set((note.tags or []) + entry["tags"]))
        store.save_note(note, author="build-multiagent",
                        summary="Added arXiv metadata + curated deep-dive analysis.")
        enriched += 1
    for c in CONCEPTS:
        note = store.get_note(c["nid"])
        note.content = concept_content_md(c)
        note.tags = sorted(set((note.tags or []) + ["concept"]))
        store.save_note(note, author="build-multiagent",
                        summary="Added concept definition and network-layer note.")
        enriched += 1

    # 6. assets manifest (copies files + writes manifest.json / README.md)
    manifest = sync_project_assets(graph, PROJECT_DIR)

    # 7. interactive export
    (PROJECT_DIR / "interactive.html").write_text(
        interactive_html(graph, title="Multi-Agent Network — Knowledge Graph"),
        encoding="utf-8")

    elapsed = time.time() - started
    return {
        "elapsed_s": round(elapsed, 1),
        "nodes": len(graph._nodes),
        "edges": len(graph._edges),
        "added_nodes": added_nodes,
        "added_edges": added_edges,
        "papers": len(PAPERS),
        "pdfs": len(pdf_map),
        "texts": len(txt_map),
        "notes_sync": res,
        "notes_enriched": enriched,
        "manifest_nodes": len(manifest),
        "graph_path": str(graph.path),
        "project_dir": str(PROJECT_DIR),
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = sys.argv[1:]
    summary = build(no_download="--no-download" in args,
                    no_extract="--no-extract" in args,
                    force_download="--force-download" in args)
    print("\n" + "═" * 72)
    print("Multi-Agent Network build complete")
    print("═" * 72)
    for k, v in summary.items():
        print(f"  {k:18s} {v}")
    print("═" * 72)
    print(f"serve with: python ui/server.py --graph {OUT_DIR}")


if __name__ == "__main__":
    main()
