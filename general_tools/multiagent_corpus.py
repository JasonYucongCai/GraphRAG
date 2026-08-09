"""
tools.multiagent_corpus — the curated Multi-Agent Network corpus.

The authoritative data for the multi-agent knowledge network: 21 papers with
deep-dive analyses (contribution / method / key results / findings /
significance, all grounded in the full extracted texts of the papers), 28
cross-cutting concept nodes, and ~150 typed edges (paper→concept,
paper→paper citations derived from the papers' actual reference lists, and
concept→concept structure).

Each paper entry has:
  nid, aid (arXiv id), takeaway (one-line), tags, contribution, method,
  key_results (numbers from the paper), findings, significance.
"""

PAPERS: list[dict] = [
    # ═══════════════════════════════════════════════════════════════════════
    # 1 — LLM multi-agent frameworks
    # ═══════════════════════════════════════════════════════════════════════
    dict(
        nid="auto_gen", aid="2308.08155",
        takeaway="The conversable-agent framework: multi-agent conversation as the "
                 "programming primitive for next-generation LLM applications.",
        tags=["framework", "conversation", "microsoft"],
        contribution="AutoGen (Microsoft Research) generalizes LLM applications into "
            "multi-agent conversations. It introduces *conversable agents* "
            "(LLM-backed, tool-backed, human-backed or hybrid) and "
            "*conversation programming* — a paradigm in which conversation-"
            "centric computation and conversation-driven control flow replace "
            "monolithic single-agent pipelines.",
        method="Agents expose unified conversation interfaces (send/receive/"
            "generate_reply) with an auto-reply mechanism: once a message is "
            "received, the agent replies automatically unless a termination "
            "condition holds — no central control plane needed. Built-ins: "
            "ConversableAgent, AssistantAgent, UserProxyAgent (human input + "
            "code/function execution), GroupChatManager (dynamic speaker "
            "selection in group chat). Control fuses natural language (system "
            "messages, TERMINATE token) and Python (reply functions, "
            "termination conditions, human-input modes).",
        key_results="MATH level-5: AutoGen 69.48% vs ChatGPT+Code Interpreter 52.5%, "
            "vanilla GPT-4 30.0%, Multi-Agent Debate 23.33%. Natural Questions "
            "(GPT-3.5): F1 66.65% with interactive retrieval ('UPDATE CONTEXT') "
            "vs 62.59% without. ALFWorld: 3-agent (grounding) 77% avg vs "
            "2-agent 63% vs ReAct 54% (+15% from grounding agent). OptiGuide "
            "coding: multi-agent raises unsafe-code F1 by +8% (GPT-4) and +35% "
            "(GPT-3.5); core code cut 430→100 lines; ~3× user time saved, "
            "3–5× fewer interactions.",
        findings="A grounding agent that injects commonsense knowledge breaks error "
            "loops in embodied decision making (ALFWorld). Role-play prompts in "
            "dynamic group chat improve speaker selection (higher success, "
            "fewer LLM calls). A board agent that validates moves is essential "
            "for game integrity (Conversational Chess ablation).",
        significance="One of the most adopted open-source multi-agent frameworks; its "
            "conversable-agent + group-chat design and human-in-the-loop "
            "patterns became the reference for later frameworks (DyLAN, MAS "
            "surveys, AutoAgents)."),
    dict(
        nid="metagpt", aid="2308.00352",
        takeaway="A simulated software company: Standardized Operating Procedures "
                 "(SOPs) turn LLM roles into an assembly line that writes code.",
        tags=["framework", "software-development", "roles"],
        contribution="MetaGPT (ICLR 2024) is a meta-programming framework that encodes "
            "human Standardized Operating Procedures (SOPs) into prompts for "
            "LLM-based multi-agent collaboration, organizing agents as a "
            "simulated software company: Product Manager → Architect → Project "
            "Manager → Engineer → QA Engineer.",
        method="Roles communicate via *structured outputs* — PRDs with user stories, "
            "system designs with file lists/data structures/interface "
            "definitions, flowcharts — instead of free-text dialogue, "
            "minimizing cascading hallucinations ('idle chatter'). A shared "
            "message pool with publish–subscribe lets agents consume only "
            "role-relevant artifacts. An *executable feedback* loop runs the "
            "engineer's code, executes unit tests and iterates up to 3 retries.",
        key_results="Pass@1: HumanEval 85.9%, MBPP 87.7% (SoTA at publication, "
            "vs GPT-4 67.0/82.3). Executable feedback adds +4.2% (HumanEval) "
            "and +5.4% (MBPP). SoftwareDev benchmark: executability 3.75 (of "
            "4) vs ChatDev 2.25; human-revision cost 0.83 vs ChatDev 2.5; "
            "124.3 tokens/line vs ChatDev 248.9; 100% task completion on 7 "
            "representative tasks.",
        findings="Ablations: removing roles collapses quality — engineer-only "
            "executability 1.0, +all 4 roles → 4.0. Structured intermediate "
            "outputs are the key anti-hallucination device; executable "
            "feedback cuts human revision cost 2.25→0.83.",
        significance="Shows human organizational structure (SOPs, roles, structured "
            "artifacts) substantially improves multi-agent software generation "
            "— the canonical role-based agent organization result."),
    dict(
        nid="chatdev", aid="2307.07924",
        takeaway="A chat-chain software company: CEO/CTO/engineer agents build "
                 "complete apps through staged instructor–assistant dialogues.",
        tags=["framework", "software-development", "chat-chain"],
        contribution="ChatDev (Tsinghua) organizes agents into a *chat chain* mirroring "
            "the waterfall model — design → coding → testing — where each "
            "subtask is a two-agent dialogue between an instructor and an "
            "assistant (CEO, CTO, programmer, reviewer, tester roles), with "
            "solutions extracted from their multi-turn consensus.",
        method="Language as a unifying bridge: natural-language subtasks (system "
            "design) and programming-language subtasks (debugging) are chained "
            "so outputs of one phase seed the next (long-term memory shares "
            "only phase solutions, short-term memory keeps within-phase "
            "dialogue). *Communicative dehallucination* lets the assistant "
            "request more specific details from the instructor before "
            "answering, reducing coding hallucinations.",
        key_results="On SRDD (1,200 requirements across Education/Work/Life/Game/"
            "Creation, 40 subcategories): Quality 0.3953 vs MetaGPT 0.1523, "
            "GPT-Engineer 0.1419; Executability 0.8800 vs 0.4145/0.3583. "
            "Pairwise: ChatDev beats GPT-Engineer 77.08% and MetaGPT 57.08% "
            "(GPT-4 eval). Removing roles drops executability 0.88→0.58; "
            "removing communicative dehallucination drops Quality "
            "0.3953→0.3094. 57.2% of utterances are natural language, 42.8% "
            "programming language.",
        findings="Multi-phase communication progressively raises quality; testing "
            "phase is critical for executability; role prompts (e.g., 'prefer "
            "GUI design') directly shape generated code; agents autonomously "
            "add features beyond the requirements.",
        significance="Early demonstration that communicative multi-agent pipelines "
            "can be cheap, fast, end-to-end software factories (~148 s, "
            "~23K tokens per app) and a baseline for chain-style agent "
            "workflows."),
    dict(
        nid="camel", aid="2303.17760",
        takeaway="Role-playing communicative agents — the inception-prompting recipe "
                 "for 'AI societies' where agents cooperate on tasks.",
        tags=["framework", "role-playing", "ai-society"],
        contribution="CAMEL (NeurIPS 2023, KAUST) proposes *role-playing* as a scalable "
            "technique for autonomous cooperation between communicative "
            "agents: an AI user (task planner/instructor) and an AI assistant "
            "(task executor) cooperate through instruction–solution pairs, "
            "guided by *inception prompting*.",
        method="Inception prompting has three parts: a task-specifier prompt (turns a "
            "coarse idea into a concrete task), the assistant system prompt, "
            "and the user system prompt — engineered to prevent role flipping, "
            "repeated instructions, flake replies and infinite loops "
            "(e.g., '<CAMEL_TASK_DONE>' end-of-task token, 'Never flip "
            "roles!', one instruction at a time). A critic-in-the-loop enables "
            "tree-search-like decision making.",
        key_results="Generated 25,000 AI-Society conversations (50 assistant roles × "
            "50 user roles × 10 tasks) + Code/Math/Science datasets. CAMEL "
            "solutions beat gpt-3.5-turbo single-shot: 76.3% win (human eval) "
            "and 73.0%/76.0% (GPT-4 eval) on AI Society/Code. Progressive "
            "LLaMA-7B fine-tuning shows knowledge emergence; CAMEL-7B reaches "
            "HumanEval pass@1 14.0% / pass@100 57.9% vs LLaMA-7B 10.5/36.5.",
        findings="Four failure modes of naive agent cooperation (role flipping, "
            "instruction repetition, flake replies, infinite message loops) "
            "and prompt designs that suppress them; generated conversations "
            "are reusable instruction-following data (fine-tuning corpus).",
        significance="One of the earliest and most-cited LLM multi-agent works; "
            "inception prompting and the role-playing pattern underpin "
            "ChatDev, AgentVerse, MetaGPT and the Agents framework."),
    dict(
        nid="agentverse", aid="2308.10848",
        takeaway="A unified framework for multi-agent problem solving AND "
                 "multi-agent simulation, with a four-stage collaboration pipeline.",
        tags=["framework", "simulation", "emergent-behavior"],
        contribution="AgentVerse (Tsinghua) unifies multi-agent problem solving and "
            "multi-agent simulation in one framework modeled as an MDP "
            "(S, A, T, R, G) with four stages: expert recruitment, "
            "collaborative decision making, action execution, and evaluation "
            "(feedback loops back to recruitment, dynamically adjusting the "
            "group).",
        method="Expert recruitment: an LLM 'recruiter' generates expert descriptions "
            "for the goal (no manual roles). Decision making supports "
            "horizontal (democratic ensemble) and vertical (solver + "
            "reviewers iterating to consensus) communication structures. "
            "Case studies: disaster-rescue NLP teams and Minecraft building/"
            "combat societies.",
        key_results="Zero-shot gains over CoT (GPT-3.5/GPT-4): FED 85.1/96.8 vs "
            "81.6/95.4; Creative Writing 92.3/99.1 vs 76.6/95.9; MGSM "
            "80.8/95.2; Logic Grid 66.5 (GPT-4). Group setup can underperform "
            "solo with GPT-3.5: ~10% of MGSM errors traced to agents being "
            "swayed by incorrect feedback — absent in GPT-4.",
        findings="Emergent collaborative behaviors: volunteering (agents help peers), "
            "conformity (agents align to group under criticism), and "
            "destructive behaviors (harmful conformity) — evidence that "
            "agent societies exhibit both beneficial and risky group dynamics.",
        significance="Bridges problem-solving and simulation paradigms and documents "
            "the failure mode of 'erroneous feedback sway' — a key caution "
            "for collaborative design."),
    dict(
        nid="autoagents", aid="2309.17288",
        takeaway="Automatic agent generation: an observer LLM dynamically creates a "
                 "specialized agent team for each new task.",
        tags=["framework", "dynamic-teams", "agent-generation"],
        contribution="AutoAgents (PKU) removes fixed role assignments: a drafting stage "
            "synthesizes a customized agent team + execution plan per task, "
            "then an execution stage runs it. Three predefined agents — "
            "Planner, Agent Observer, Plan Observer — iterate to validate "
            "team composition and plan quality.",
        method="Each generated agent is a tuple {prompt, description, toolset, "
            "suggestions}. Execution uses vertical communication led by an "
            "Action Observer (team leader), with two action types: "
            "self-refinement (single agent think-plan-execute-feedback loop) "
            "and collaborative refinement (agents refine in fixed turn order). "
            "Three-tier memory: short-term (per action), long-term (task "
            "history), dynamic (Action Observer extracts from long-term). "
            "Built on MetaGPT's environment.",
        key_results="Open-ended QA (MT-bench): beats ChatGPT 96.3% and Vicuna-13B "
            "96.3% (FairEval), beats GPT-4 76.3% (FairEval) / 62.5% (human). "
            "Also evaluated on Trivia Creative Writing and case studies "
            "(novel writing, software development).",
        findings="Dynamic agents matter for complex tasks; self-refinement is "
            "indispensable for proficient agents; collaborative conversation "
            "improves knowledge integration across specialties.",
        significance="Establishes the dynamic-team paradigm (agent generation at "
            "inference time) later refined by DyLAN's principled selection."),
    dict(
        nid="agents_framework", aid="2309.07870",
        takeaway="The open-source 'Agents' framework: a practical implementation of "
                 "the CAMEL architecture with pluggable roles, tools and memory.",
        tags=["framework", "open-source", "camel-ecosystem"],
        contribution="AGENTS (AIWaves/ETH) is an open-source library making autonomous "
            "language agents accessible to non-specialists: planning, "
            "long/short-term memory, tool usage, web navigation, multi-agent "
            "communication with *dynamic scheduling*, human-agent "
            "interaction, and fine-grained *symbolic control* via SOPs.",
        method="Three core classes from a plain-text config: Agent (observe → act → "
            "update memory; any agent can be human via is_human flag), SOP "
            "(a graph of states with per-state prompt/tool components; "
            "LLM-based state transition and agent routing), Environment "
            "(observation and update functions). Dynamic scheduling uses a "
            "controller agent as moderator choosing the next speaker. An "
            "automated SOP-generation pipeline (RAG-based 'meta agent') "
            "writes configs from a task description.",
        key_results="Feature comparison table: the only framework of its class "
            "supporting tool usage + long/short-term memory + multi-agent "
            "communication + human-agent interaction + symbolic control "
            "simultaneously. Case studies: customer service, sales, fiction "
            "studio (editor + writer), human-in-debate.",
        findings="Symbolic plans (SOPs) make agent behavior stable/predictable and "
            "tunable; the meta-agent pipeline can generate whole multi-agent "
            "systems from one sentence; deployment via FastAPI + Agent Hub "
            "for sharing.",
        significance="Reference open-source implementation of the CAMEL architecture, "
            "showing how role-playing, tool use, memory and SOP control "
            "compose into production-grade agent systems."),
    # ═══════════════════════════════════════════════════════════════════════
    # 2 — collaboration mechanisms
    # ═══════════════════════════════════════════════════════════════════════
    dict(
        nid="collab_llm", aid="2306.03314",
        takeaway="Early framework + survey of multi-agent collaboration: agents as "
                 "graph nodes with roles, plugins, feedback and supervision.",
        tags=["survey", "collaboration", "framework"],
        contribution="Talebirad & Nadiri propose a general framework for 'Intelligent "
            "Generative Agents' (IGAs): a black-box graph G(V, E) where "
            "agents Ai = (Li, Ri, Si, Ci, Hi) (LLM instance, role, state, "
            "agent-creation ability, halt authority) and plugins Pj = (Fj, "
            "Cj, Uj) (functions, configs, usage constraints) are vertices, "
            "messages m = (Sm, Am, Dm) are edges.",
        method="System design (roles, agent-plugin/agent-agent connections, "
            "permissions), dynamic addition of agents (creator agents spawn "
            "and supervise), inter-agent and self-feedback (incl. inception-"
            "prompting role-play), stateless *oracle agents*, halting "
            "mechanisms and a supervisor agent, and LLM-driven autonomous "
            "system design.",
        key_results="Case-study analysis (no benchmark): models Auto-GPT and BabyAGI "
            "in the framework; shows supervisor agents and oracle agents can "
            "mitigate looping, off-task drift and security risks; court "
            "simulation and software development scenarios.",
        findings="Identifies the core failure modes of chained-thought agents "
            "(loops, task drift, security) and the framework elements that "
            "counter them; positions multi-agent collaboration as a path "
            "toward AGI.",
        significance="Early systematization of multi-agent design space; its graph "
            "abstraction (agents/plugins/messages) anticipates later "
            "network-based models like DyLAN."),
    dict(
        nid="social_psych", aid="2310.02124",
        takeaway="Collaboration through a social-psychology lens: agent traits, "
                 "debate/reflection thinking patterns, and machine societies.",
        tags=["survey", "social-psychology", "collaboration"],
        contribution="MachineSoM (Zhejiang University) probes LLM collaboration "
            "mechanisms through social psychology: four 3-agent 'societies' "
            "built from two individual traits (easy-going vs overconfident) "
            "and two thinking patterns (debate vs reflection) permuted into "
            "eight 3-round collaborative strategies.",
        method="Agents with trait-conditioned system prompts ('I can be persuaded "
            "if…' vs 'I am confident and persuade others') collaborate "
            "round by round; each round every agent either debates (reads "
            "and critiques others' answers) or reflects (reviews and revises "
            "its own). Evaluated on MMLU (50), MATH L3–5 (50) and Chess "
            "Move Validity (BIG-Bench), with WIN-TIE and token-cost metrics.",
        key_results="Debate-initial strategies dominate: p0p0p0/p0p0p1 outperform "
            "reflection-initial strategies by wide margins (e.g., MMLU S4: "
            "65.2 for p0p0p1 vs 34.4 for p1p0p0). Societies with different "
            "traits do NOT differ significantly in accuracy (LLM alignment "
            "suppresses extreme traits), but easy-going societies reach "
            "consensus more. Optimal configuration: 3 agents (odd numbers "
            "avoid ties), 3 rounds; more agents/rounds do not reliably help. "
            "Cost drops from 4,364 to 1,976 tokens across strategies.",
        findings="LLM agents manifest human-like conformity and majority-rule "
            "behavior; debate+continuous reflection wins on the hardest "
            "tasks (MATH level 5); uniform thinking pattern within a round "
            "improves efficiency.",
        significance="Brings a scientific lens to agent collaboration design and "
            "empirically grounds the 'small group, rational strategy' "
            "view over naive scaling."),
    dict(
        nid="spp", aid="2307.05300",
        takeaway="Solo Performance Prompting: one LLM playing multiple expert "
                 "personas simulates multi-agent cognitive synergy at "
                 "single-agent cost.",
        tags=["prompting", "multi-persona", "single-agent"],
        contribution="SPP (UIUC + Microsoft Research Asia) turns a single LLM into a "
            "*cognitive synergist*: it dynamically identifies multiple "
            "personas needed for the task, has them brainstorm, then runs "
            "multi-persona iterative collaboration (leader drafts, "
            "participants critique, revision) — all inside one context.",
        method="Zero-shot prompting with a 3-stage procedure: persona "
            "identification (dynamic, task-dependent; e.g., a 'Jay Chou "
            "Fan' persona for music trivia), brainstorming, and iterative "
            "collaboration between the AI-Assistant leader persona and the "
            "identified participants. Two demonstration examples in the "
            "prompt.",
        key_results="Evaluated on Trivia Creative Writing, Codenames Collaborative, "
            "Logic Grid Puzzle. Cognitive synergy emerges ONLY in GPT-4 — "
            "GPT-3.5-turbo and Llama2-13b-chat show no gain (analogy to "
            "role-play emerging in human development). Fine-grained dynamic "
            "personas beat fixed/coarse personas (vs CAMEL-style fixed and "
            "ExpertPrompting-style profile variants); reduces factual "
            "hallucination while keeping reasoning strength.",
        findings="Assigning multiple fine-grained personas improves problem solving "
            "vs a single or fixed number of personas; the multi-persona "
            "effect is an emergent capability of stronger models.",
        significance="Blurs the single/multi-agent boundary: multi-agent-like gains "
            "are available inside one context at ~1/10th the token cost of "
            "multi-agent debate — key for cost-constrained deployments."),
    dict(
        nid="debate", aid="2305.14325",
        takeaway="Multiagent debate: agents propose, read each other's answers and "
                 "argue — improving factuality and reasoning on hard tasks.",
        tags=["debate", "reasoning", "factuality"],
        contribution="Du et al. (MIT/Google Brain) introduce multiagent debate as a "
            "complementary 'society of minds' approach: multiple LLM "
            "instances generate answers, read each other's answers and "
            "reasoning, and revise over rounds until consensus — pure "
            "black-box, same prompts for all tasks, orthogonal to CoT.",
        method="Each agent independently solves the task, then receives all other "
            "agents' solutions as context and produces an updated response; "
            "repeated for N rounds; final answer aggregated. Debate duration "
            "is controllable via prompt phrasing ('stubborn' prompts → "
            "longer, better debates). Consensus analysis shows agents are "
            "'agreeable' due to RLHF alignment.",
        key_results="Reasoning: Arithmetic 81.8% vs single 67.0%; GSM8K 85.0% vs "
            "77.0%; Chess next-move ΔPS 122.9 vs 91.4 (3 agents, 2 rounds). "
            "Factuality: Biographies (new 524-person benchmark) 73.8 vs "
            "66.0; MMLU 71.1 vs 63.9; Chess Move Validity 45.2 vs 29.3. "
            "Performance rises monotonically with agent count and rounds "
            "(saturating ~4 rounds).",
        findings="Debate converges to a single accurate answer even when ALL agents "
            "start wrong; uncertain facts are dropped (agents disagree and "
            "omit); 'ease of persuasion' tracks factual confidence — "
            "confident facts resist debate, uncertain ones flip fast.",
        significance="The canonical debate paper — generate, read others, revise — "
            "recurring in DyLAN, social-psychology studies and later "
            "systems."),
    dict(
        nid="dylan", aid="2310.02170",
        takeaway="DyLAN: agents as a temporal feed-forward network — dynamic team "
                 "optimization selects the right collaborators per task.",
        tags=["framework", "dynamic-teams", "agent-network"],
        contribution="DyLAN (Tsinghua/Stanford, COLM 2024) models LLM-agent "
            "collaboration explicitly as a *temporal feed-forward network* "
            "(T-FFN): nodes are agents at time steps, edges are "
            "communication channels. Two stages: Team Optimization (select "
            "the best agents by contribution) then Task Solving (dynamic "
            "collaboration with team reformation).",
        method="Agent Importance Score: a forward-backward message-passing "
            "algorithm inspired by backpropagation — each node peer-rates "
            "predecessors' responses (propagation), successors' weighted "
            "ratings aggregate backward (aggregation), per-agent scores sum "
            "over layers (selection). Task solving runs the T-FFN forward "
            "with an LLM ranker deactivating low performers mid-run, plus "
            "Byzantine-consensus early stopping (≥2/3 consistent answers).",
        key_results="Code generation Pass@1 82.9 vs single execution 73.2, CAMEL "
            "69.5, AgentVerse 75.0, LATS 81.1 (16.85 API calls vs LATS 48). "
            "Decision making: reward 68.3 vs BOLAA 66.0, LATS 64.5, "
            "Reflexion 62.0. MMLU: up to +25.0% accuracy on specific "
            "subjects from team selection. Also strong on arithmetic "
            "reasoning.",
        findings="Agent teams are optimizable structure: pruning low-contributing "
            "agents improves accuracy AND cuts cost; importance scores "
            "correlate with task relevance; dynamic reformation adapts to "
            "query content.",
        significance="First principled treatment of the agent team as an optimizable "
            "network — connects multi-agent systems with network science "
            "and directly relevant to this knowledge-network project."),
    # ═══════════════════════════════════════════════════════════════════════
    # 3 — surveys
    # ═══════════════════════════════════════════════════════════════════════
    dict(
        nid="mas_survey", aid="2402.03578",
        takeaway="Challenges and open problems of LLM multi-agent systems: task "
                 "allocation, debate loops, layered context, memory, and "
                 "blockchain applications.",
        tags=["survey", "challenges"],
        contribution="Han et al. survey LLM multi-agent systems through their open "
            "problems: optimizing task allocation across specialized "
            "agents, robust reasoning via iterative debate sub-loops, "
            "managing layered context (global task / per-agent / shared "
            "knowledge), and multi-objective memory management; explores "
            "blockchain as a distributed application domain.",
        method="Taxonomy of MAS structures — equi-level, hierarchical (incl. "
            "Stackelberg leader-follower), nested/hybrid, dynamic — then "
            "per-component analysis: global vs local (per-agent) planning, "
            "task decomposition formats (CoT, multiple CoTs, PoT, Tab-CoT, "
            "ToT), game-theoretic grounding (Nash, Stackelberg equilibria), "
            "memory management, and applications on distributed systems.",
        key_results="No benchmark results (position/challenges paper); establishes "
            "the research agenda: definition of payoff structures, "
            "equilibrium computation, context alignment across agents, "
            "memory designs for agent interaction histories, and two "
            "blockchain integration modes (MAS as tool; agent per "
            "blockchain node).",
        findings="MAS capabilities far exceed current progress; the field lacks "
            "standardized protocols for context and memory sharing; "
            "game theory offers a well-structured framework for debate/"
            "discussion interactions.",
        significance="Frames the frontier of LLM-MAS research — complements the "
            "workflow surveys and the collaboration taxonomies."),
    dict(
        nid="rise_survey", aid="2309.07864",
        takeaway="'The Rise and Potential of LLM-based Agents': brain/perception/"
                 "action architecture and capability acquisition across "
                 "100+ papers.",
        tags=["survey", "agent-architecture"],
        contribution="Xi et al. survey LLM-based agents (100+ papers) around a "
            "three-layer architecture — brain (the LLM reasoning core), "
            "perception (multimodal inputs), action (tools, environment "
            "interaction) — plus the capability-acquisition loop "
            "(fine-tuning, RLHF, in-context learning) and applications "
            "including multi-agent collaboration.",
        method="Taxonomy-driven review organizing agents by architecture layers, "
            "capability acquisition strategies (training-based vs "
            "in-context), and application domains (single-agent, "
            "multi-agent, human-agent); ends with evaluation and open "
            "problems.",
        key_results="Survey of 100+ papers (no single benchmark); establishes the "
            "brain-perception-action vocabulary, catalogs memory and "
            "planning as cross-cutting modules, and identifies "
            "multi-agent collaboration as a core application class with "
            "coordination challenges (communication, cooperation, "
            "competition).",
        findings="The field converged on the modular architecture pattern; "
            "capability acquisition via feedback (Reflexion-style), "
            "tool learning and fine-tuning are the levers of agent "
            "progress.",
        significance="The most-cited LLM-agent survey; its architecture diagram is "
            "common vocabulary for agent papers."),
    dict(
        nid="autonomous_survey", aid="2308.11432",
        takeaway="Survey of LLM-based autonomous agents: profiling, memory, "
                 "planning and action as the four modules.",
        tags=["survey", "autonomous-agents"],
        contribution="Wang et al. (Renmin University, published in Frontiers of "
            "Computer Science 2025) survey LLM-based autonomous agents "
            "with a unified framework of four modules — profiling (role "
            "identification), memory, planning, action — plus capability "
            "acquisition, applications and evaluation strategies.",
        method="Profiling: handcrafting (Generative Agents, MetaGPT, ChatDev), "
            "LLM-generation (RecAgent), dataset alignment (ANES). Memory: "
            "structures (unified short-term vs hybrid), formats (natural "
            "language, embeddings, databases, structured lists), "
            "operations (reading, writing, reflection). Planning: with/"
            "without feedback, single/multi-path reasoning, external "
            "planners. Action: targets (tools, databases, lists), "
            "production, impact.",
        key_results="Survey taxonomy (no benchmark); documents the agent timeline "
            "2021–2023 (WebGPT → Generative Agents → Voyager → ToolBench), "
            "and evaluates subjective (human/LLM scoring) and objective "
            "evaluation strategies for agents.",
        findings="Memory and planning are the main levers for long-horizon "
            "autonomy; multi-agent coordination amplifies both "
            "capabilities and failure modes; open problems in "
            "evaluation, safety and scalability.",
        significance="Complements the Rise survey with an autonomy-focused "
            "component model; the reference for memory/tool taxonomies."),
    # ═══════════════════════════════════════════════════════════════════════
    # 4 — memory & society
    # ═══════════════════════════════════════════════════════════════════════
    dict(
        nid="generative_agents", aid="2304.03442",
        takeaway="25 believable agents in 'Smallville': memory streams, reflection "
                 "and planning produce emergent social behavior.",
        tags=["simulation", "memory", "emergent-behavior"],
        contribution="Generative Agents (Stanford, UIST '23) embed LLMs in an "
            "interactive sandbox (Smallville) with 25 agents who wake, "
            "work, socialize and plan. Introduces the *memory stream* "
            "architecture: natural-language records of experience, "
            "retrieval scored by recency+importance+relevance, "
            "higher-level *reflections*, and reactive + deliberative "
            "*planning* feeding back into memory.",
        method="Each agent stores timestamped observations; retrieval surfaces "
            "relevant memories; periodic reflection synthesizes insights "
            "('I want to throw a Valentine's party'); planning expands "
            "intentions into actions executed in the world; agents "
            "communicate in natural language. Evaluated via 'interviews' "
            "(control: stay in character, remember, plan, react, reflect) "
            "and an end-to-end 2-day simulation.",
        key_results="From ONE user seed ('Isabella wants a Valentine's Day party'), "
            "invitations spread through the social graph over 2 days, "
            "acquaintances form, agents ask each other out, and attendees "
            "show up on time. Controlled evaluation: ablations removing "
            "memory, reflection, or planning each significantly degrade "
            "interview performance. Most common errors: failed memory "
            "retrieval, fabricated embellishments, overly formal speech.",
        findings="Emergent, believable social phenomena (rumor spread, friendship "
            "formation, coordination) — the canonical agent-society "
            "demonstration; components contribute critically to "
            "believability.",
        significance="The ancestor of most agent-memory architectures; directly "
            "informed the memory-stream/reflection designs used by later "
            "frameworks and this project's note-VCL design."),
    # ═══════════════════════════════════════════════════════════════════════
    # 5 — evaluation
    # ═══════════════════════════════════════════════════════════════════════
    dict(
        nid="agentbench", aid="2308.03688",
        takeaway="AgentBench: 8 environments (OS, DB, web, games…) expose the "
                 "large gap between frontier and open models as agents.",
        tags=["evaluation", "benchmark"],
        contribution="AgentBench (Tsinghua/OSU/Berkeley, ICLR 2024) is a "
            "multi-dimensional benchmark evaluating LLMs as agents across "
            "8 environments in 3 grounding types — code (operating "
            "system, database, knowledge graph), game (digital card game, "
            "lateral thinking puzzles, house-holding), web (shopping, "
            "browsing) — formalized as a POMDP (S, A, T, R, U, O).",
        method="29 API-based and open-source LLMs evaluated with a unified "
            "server-client toolkit; CoT prompting as the baseline strategy; "
            "failure modes classified into Context Limit Exceeded, "
            "Invalid Format, Invalid Action, Task Limit Exceeded, and "
            "Complete.",
        key_results="Overall scores: GPT-4 4.01, Claude-3 3.11, GLM-4 2.89, "
            "GPT-3.5-turbo 2.32 (API average 2.32) vs OSS average 0.51 "
            "(CodeLlama-34b 0.96, Vicuna-13b 0.93, Llama-2-70b 0.78; "
            "ChatGLM-6b 0.11, Dolly-12b 0.14). Many OSS models below "
            "random baselines on several environments.",
        findings="Main obstacles to usable agents: poor long-term reasoning, "
            "decision making, and instruction following (Invalid Format/"
            "Action dominate); code training has ambivalent effects "
            "(helps some agent tasks, hurts others); high-quality "
            "alignment data improves agent performance.",
        significance="The de facto agent-evaluation suite 2023–24; its "
            "frontier/open gap finding drove agent fine-tuning research."),
    # ═══════════════════════════════════════════════════════════════════════
    # 6 — MARL foundations
    # ═══════════════════════════════════════════════════════════════════════
    dict(
        nid="marl_survey", aid="1911.10635",
        takeaway="Selective overview of multi-agent RL: game-theoretic foundations "
                 "and algorithmic families with convergence guarantees.",
        tags=["survey", "marl", "game-theory"],
        contribution="Zhang, Yang & Başar (UIUC/Princeton) provide a selective, "
            "theory-focused overview of MARL: Markov/stochastic games and "
            "extensive-form games as the two frameworks, organized by "
            "task type (fully cooperative, fully competitive, mixed), "
            "with convergence/complexity guarantees for each algorithm "
            "family.",
        method="Background on single-agent RL (value-based: Q-learning, SARSA, "
            "MCTS/UCT; policy-based: policy gradient, REINFORCE, "
            "actor-critic, PPO/TRPO/SAC), then MARL frameworks, "
            "challenges (non-stationarity, exponential joint action "
            "space, information structure), and theory-backed algorithms "
            "per setting — plus new angles: extensive-form games, "
            "decentralized networked MARL, mean-field regime, and "
            "(non-)convergence of policy-based methods.",
        key_results="No benchmark numbers (theory survey); establishes solution "
            "concepts (Nash, correlated, Stackelberg equilibria; "
            "equilibrium selection), convergence results for Q-learning "
            "in games, and the mean-field approximation for very large "
            "agent populations.",
        findings="Independent learning fails under non-stationarity; "
            "centralized-critic/joint-action methods mitigate at "
            "communication cost; mean-field methods scale MARL to many "
            "agents; open problems in sample efficiency and equilibrium "
            "selection.",
        significance="The standard mathematical reference for MARL — the "
            "pre-LLM foundation beneath SMAC-era deep MARL and the "
            "theory layer of this network."),
    dict(
        nid="comm_learning", aid="1605.06676",
        takeaway="DIAL & RIAL: deep MARL agents learn communication protocols "
                 "from scratch in referential games.",
        tags=["marl", "communication", "emergence"],
        contribution="Foerster et al. (Oxford) show deep multi-agent RL can learn "
            "communication protocols end-to-end: Reinforced Inter-Agent "
            "Learning (RIAL, DRQN + independent Q-learning) and "
            "Differentiable Inter-Agent Learning (DIAL, gradients flow "
            "through communication channels during centralized learning, "
            "decentralized execution).",
        method="Fully cooperative, partially observable tasks where agents act "
            "AND send limited-bandwidth discrete messages; DIAL passes "
            "real-valued messages (binarized via a DRU) between agent "
            "networks so the recipient's error backpropagates to the "
            "sender. Engineering: disable experience replay "
            "(non-stationarity), feed previous actions as inputs, "
            "parameter sharing with agent index.",
        key_results="Switch riddle (n=3,4): DIAL + parameter sharing reaches "
            "optimal fastest; for n=4, RIAL without sharing fails to beat "
            "a NoComm baseline; extracted decision tree shows the "
            "learned protocol is interpretable. MNIST/Color-MNIST/SVHN "
            "referential games: DIAL reliably outperforms RIAL and "
            "independent learners, learning effective 1-bit protocols "
            "(e.g., encoding parity over color for higher reward).",
        findings="Gradient-based communication learning is richer than pure "
            "reinforcement; parameter sharing is crucial for protocol "
            "coordination; learned protocols are grounded and "
            "interpretable.",
        significance="A founding result in emergent communication — the "
            "pre-LLM evidence that agents self-organize protocols, "
            "mirrored later in LLM agent dialogue design."),
    dict(
        nid="smac", aid="1902.04043",
        takeaway="SMAC: the StarCraft II benchmark of cooperative micro-scenarios "
                 "that exposed the limits of value-decomposition MARL.",
        tags=["marl", "benchmark", "cooperation"],
        contribution="SMAC (Oxford, NeurIPS 2019 workshop) fills the missing "
            "standardized benchmark for cooperative MARL: 14 StarCraft II "
            "micromanagement scenarios where each unit is an independent "
            "agent with local observations (sight range 9, shooting "
            "range 6), fighting the scripted game AI; formalized as "
            "Dec-POMDPs under centralized training with decentralized "
            "execution (CTDE).",
        method="Scenarios span easy → super-hard (2s3z, 3s5z, MMM2, corridor, "
            "2c_vs_64zg…) requiring focus fire, kiting, and formation "
            "skills; shaped reward (damage + kills + win bonus) or "
            "sparse ±1; open-source PyMARL framework ships QMIX, QTRAN, "
            "COMA, VDN, IQL baselines; evaluation best practices "
            "(win rate, sample efficiency, compute reporting).",
        key_results="Established the cooperative benchmark: value-decomposition "
            "methods (QMIX, VDN) beat independent learners (IQL) on most "
            "scenarios, but super-hard scenarios (2c_vs_64zg, corridor, "
            "6h_vs_8z, MMM2) remained largely unsolved by all baselines "
            "— exposing the 'cooperation gap' that drove later MARL "
            "research.",
        findings="CTDE + value decomposition are the recipe for cooperative "
            "micro; multi-agent credit assignment and joint-action "
            "representation remain open; standardized benchmarks enable "
            "reproducible progress.",
        significance="The canonical cooperative-MARL benchmark of the AlphaStar "
            "era — isolates and measures the cooperative micro-layer "
            "that value-decomposition methods must solve."),
    # ═══════════════════════════════════════════════════════════════════════
    # 7 — graph reasoning
    # ═══════════════════════════════════════════════════════════════════════
    dict(
        nid="got", aid="2308.09687",
        takeaway="Graph of Thoughts: reasoning as an arbitrary graph of LLM "
                 "thoughts, with aggregation and refinement operations.",
        tags=["prompting", "graph-reasoning", "reasoning"],
        contribution="GoT (ETH Zurich) generalizes CoT / CoT-SC / ToT by modeling "
            "the LLM reasoning process as an arbitrary directed graph: "
            "thoughts are vertices, dependencies are edges, and *thought "
            "transformations* (generation, refinement, aggregation, "
            "looping, scoring, ranking) are the operations — enabling "
            "synergistic combination of thoughts that trees/chains "
            "cannot express. Formally GoT = (G, T, E, R).",
        method="A modular architecture separates prompt, parser, scorer, "
            "controller, graph operations and LLM backends (GPT-3.5, "
            "GPT-4, Llama-2) so new thought transformations and graph "
            "patterns plug in. Evaluated on sorting, keyword counting, "
            "set operations and document merging; introduces the "
            "*volume of a thought* metric (number of thoughts that can "
            "reach it).",
        key_results="Sorting: quality +62% over ToT (and ~+70% over CoT) while "
            "cutting cost by >31% vs ToT. Keyword counting: new SoTA, "
            "+31% over ToT. 24-point game: higher success than ToT; "
            "document merging quality up; aggregate/refine operations "
            "shown to raise both accuracy and thought volume.",
        findings="Graph-structured reasoning enables aggregation (combine "
            "partial solutions) and feedback loops (refine), which "
            "linear/tree schemes cannot; best for tasks decomposable "
            "into solvable-then-mergeable subtasks.",
        significance="Establishes graph-structured (not just linear or tree) "
            "reasoning — the direct bridge between prompting research "
            "and this project's graph-based knowledge network."),
]

# ═══════════════════════════════════════════════════════════════════════════
# Concepts — cross-cutting nodes papers attach to (the network layer).
# 11 base concepts + 17 content-derived concepts.
# ═══════════════════════════════════════════════════════════════════════════

CONCEPTS: list[dict] = [
    # ── base concepts ───────────────────────────────────────────────────────
    dict(nid="multi_agent_llm_systems",
         name="Multi-Agent LLM Systems",
         desc="Systems in which multiple LLM-backed agents cooperate, compete, or mix "
              "both to solve tasks none of them could solve alone."),
    dict(nid="agent_communication",
         name="Agent Communication",
         desc="The protocols and message formats (free text, structured artifacts, "
              "differentiable channels, message pools) through which agents exchange "
              "information."),
    dict(nid="agent_roles",
         name="Agent Roles & Specialization",
         desc="Assignment of distinct functions (manager, engineer, critic, observer…) "
              "to agents, mirroring human organizational structure (SOPs, roles, "
              "status)."),
    dict(nid="agent_teams",
         name="Dynamic Agent Teams",
         desc="Inference-time formation and optimization of agent teams — generating, "
              "selecting (importance scores), and pruning collaborators per task."),
    dict(nid="multiagent_debate",
         name="Multiagent Debate",
         desc="Reasoning protocol where agents generate answers, read each other's "
              "answers, and revise over rounds until consensus or aggregation."),
    dict(nid="agent_memory",
         name="Agent Memory",
         desc="Short-term and long-term memory structures (memory streams, reflection, "
              "vector retrieval) that ground agents in their history and context."),
    dict(nid="memory_stream",
         name="Memory Streams & Reflection",
         desc="The Generative-Agents memory architecture: timestamped natural-language "
              "experience records retrieved by recency+importance+relevance, "
              "synthesized into higher-level reflections, and fed back into "
              "planning."),
    dict(nid="emergent_collaboration",
         name="Emergent Collaboration",
         desc="Self-organized cooperative behaviors (volunteering, conformity, "
              "consensus, information cascades) arising from agent interaction, for "
              "good or ill."),
    dict(nid="agent_benchmarking",
         name="Agent Benchmarking",
         desc="Standardized environments and protocols for measuring agent capability "
              "(tool use, planning, long-horizon tasks, cooperation)."),
    dict(nid="marl",
         name="Multi-Agent Reinforcement Learning",
         desc="RL with multiple learning agents sharing an environment — Markov games, "
              "Dec-POMDPs, game theory, independent/joint-action learning, CTDE."),
    dict(nid="graph_based_reasoning",
         name="Graph-Based Reasoning",
         desc="Structuring LLM reasoning (or agent collaboration) as a graph — nodes "
              "are thoughts/agents, edges are dependencies or communication."),
    dict(nid="software_agents",
         name="Software Development Agents",
         desc="Application domain: multi-agent pipelines that analyze requirements, "
              "design, code, test and document software."),
    # ── content-derived concepts ────────────────────────────────────────────
    dict(nid="conversation_programming",
         name="Conversation Programming",
         desc="AutoGen's paradigm: LLM application workflows are programmed as "
              "multi-agent conversations — conversation-centric computation plus "
              "conversation-driven control flow (send/receive/generate_reply, "
              "auto-reply, termination conditions)."),
    dict(nid="inception_prompting",
         name="Inception Prompting",
         desc="CAMEL's prompting technique: task-specifier prompt + role system "
              "prompts engineered up front so agents prompt each other autonomously "
              "until an end-of-task token — suppressing role flipping, flake "
              "replies, and infinite loops."),
    dict(nid="sop_workflows",
         name="Standardized Operating Procedures (SOPs)",
         desc="Encoding human SOPs into agent workflows: predefined role pipelines, "
              "structured intermediate artifacts and state-graph plans that make "
              "multi-agent behavior controllable and reproducible."),
    dict(nid="structured_communication",
         name="Structured Communication",
         desc="Replacing free-text dialogue with machine-readable artifacts (PRDs, "
              "design docs, interface specs, message pools with publish–subscribe) "
              "to reduce cascading hallucinations and information loss."),
    dict(nid="executable_feedback",
         name="Executable Feedback",
         desc="Self-correction via actually running generated code/tests and feeding "
              "execution results back into the agent loop — beyond non-executable "
              "review/reflection."),
    dict(nid="role_playing",
         name="Role-Playing Collaboration",
         desc="Cooperation through assigned roles (assistant/user, instructor/"
              "assistant, persona sets): role-play elicits expertise, structure and "
              "task decomposition from LLMs."),
    dict(nid="multi_persona_prompting",
         name="Multi-Persona Prompting",
         desc="Simulating a team inside ONE LLM context: dynamic persona "
              "identification, brainstorming and iterative self-collaboration — "
              "multi-agent-like gains at single-agent cost."),
    dict(nid="emergent_communication",
         name="Emergent Communication",
         desc="Learned communication protocols: agents discover messages/meanings "
              "end-to-end (differentiable channels, referential games) rather than "
              "following pre-specified protocols."),
    dict(nid="ctde",
         name="Centralized Training / Decentralized Execution",
         desc="The CTDE paradigm: algorithms exploit global state during training "
              "(critics, value decomposition, differentiable channels) while "
              "execution policies condition only on local observations."),
    dict(nid="value_decomposition",
         name="Value Decomposition",
         desc="Factorizing the joint action-value function into per-agent utilities "
              "(VDN, QMIX) to solve cooperative credit assignment in Dec-POMDPs."),
    dict(nid="agent_architectures",
         name="Agent Architectures",
         desc="The modular anatomy of agents: brain/perception/action (Rise survey) "
              "and profiling/memory/planning/action (Autonomous survey) — the "
              "shared vocabulary of agent design."),
    dict(nid="tool_use",
         name="Tool Use & External APIs",
         desc="Agents invoking tools, code execution, web search and APIs to act "
              "beyond language — a core capability in frameworks and benchmarks."),
    dict(nid="planning",
         name="Planning & Task Decomposition",
         desc="Breaking tasks into subtasks and scheduling them (global plans across "
              "agents, local per-agent plans; chain/tree/graph decomposition "
              "formats; plan generation and revision)."),
    dict(nid="simulated_societies",
         name="Simulated Societies",
         desc="Sandbox worlds (Smallville, Minecraft, rescue scenarios) where agent "
              "societies are studied for emergent social behavior, believability "
              "and group dynamics."),
    dict(nid="game_theory_mas",
         name="Game Theory for MAS",
         desc="Strategic-interaction foundations: Nash/Stackelberg/correlated "
              "equilibria, leader-follower hierarchies, debate as multi-agent "
              "games, and equilibrium computation in Markov games."),
    dict(nid="hallucination_mitigation",
         name="Hallucination Mitigation",
         desc="Mechanisms that reduce factual errors and coding hallucinations in "
              "agent pipelines: debate, structured outputs, executable feedback, "
              "communicative dehallucination, multi-persona grounding."),
]

# ═══════════════════════════════════════════════════════════════════════════
# Edges — (source, target, relation). Papers↔concepts, paper↔paper (cites /
# extends / related_to, grounded in the papers' actual reference lists),
# concept↔concept (part_of / example_of / related_to).
# ═══════════════════════════════════════════════════════════════════════════

EDGES: list[tuple[str, str, str]] = [
    # ── papers → base concepts ──────────────────────────────────────────────
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
    # ── papers → content-derived concepts ───────────────────────────────────
    ("auto_gen", "conversation_programming", "introduces"),
    ("auto_gen", "tool_use", "implements"),
    ("auto_gen", "hallucination_mitigation", "related_to"),
    ("metagpt", "sop_workflows", "introduces"),
    ("metagpt", "structured_communication", "introduces"),
    ("metagpt", "executable_feedback", "introduces"),
    ("metagpt", "role_playing", "uses"),
    ("chatdev", "inception_prompting", "uses"),
    ("chatdev", "hallucination_mitigation", "addresses"),
    ("chatdev", "role_playing", "uses"),
    ("camel", "inception_prompting", "introduces"),
    ("camel", "role_playing", "introduces"),
    ("camel", "hallucination_mitigation", "related_to"),
    ("agentverse", "simulated_societies", "uses"),
    ("agentverse", "planning", "uses"),
    ("agentverse", "hallucination_mitigation", "related_to"),
    ("autoagents", "agent_architectures", "extends"),
    ("autoagents", "executable_feedback", "uses"),
    ("autoagents", "planning", "implements"),
    ("agents_framework", "sop_workflows", "implements"),
    ("agents_framework", "tool_use", "implements"),
    ("agents_framework", "agent_memory", "implements"),
    ("agents_framework", "emergent_communication", "cites"),
    ("collab_llm", "role_playing", "surveys"),
    ("collab_llm", "inception_prompting", "cites"),
    ("social_psych", "role_playing", "surveys"),
    ("social_psych", "game_theory_mas", "related_to"),
    ("social_psych", "simulated_societies", "uses"),
    ("spp", "multi_persona_prompting", "introduces"),
    ("spp", "role_playing", "uses"),
    ("spp", "hallucination_mitigation", "addresses"),
    ("debate", "hallucination_mitigation", "addresses"),
    ("debate", "game_theory_mas", "related_to"),
    ("dylan", "graph_based_reasoning", "uses"),
    ("dylan", "conversation_programming", "related_to"),
    ("mas_survey", "planning", "surveys"),
    ("mas_survey", "agent_memory", "surveys"),
    ("mas_survey", "game_theory_mas", "surveys"),
    ("mas_survey", "agent_architectures", "surveys"),
    ("rise_survey", "agent_architectures", "introduces"),
    ("rise_survey", "tool_use", "surveys"),
    ("rise_survey", "planning", "surveys"),
    ("autonomous_survey", "agent_architectures", "introduces"),
    ("autonomous_survey", "planning", "surveys"),
    ("autonomous_survey", "tool_use", "surveys"),
    ("autonomous_survey", "memory_stream", "surveys"),
    ("generative_agents", "memory_stream", "introduces"),
    ("generative_agents", "simulated_societies", "introduces"),
    ("generative_agents", "planning", "implements"),
    ("agentbench", "tool_use", "evaluates"),
    ("agentbench", "planning", "evaluates"),
    ("marl_survey", "game_theory_mas", "surveys"),
    ("marl_survey", "ctde", "surveys"),
    ("marl_survey", "value_decomposition", "surveys"),
    ("comm_learning", "emergent_communication", "introduces"),
    ("comm_learning", "ctde", "uses"),
    ("smac", "ctde", "uses"),
    ("smac", "value_decomposition", "uses"),
    ("got", "graph_based_reasoning", "defines"),
    ("got", "planning", "related_to"),
    # ── paper → paper (citations grounded in the texts' reference lists) ────
    ("auto_gen", "camel", "cites"),
    ("auto_gen", "debate", "cites"),
    ("auto_gen", "metagpt", "cites"),
    ("auto_gen", "generative_agents", "cites"),
    ("auto_gen", "rise_survey", "cites"),
    ("auto_gen", "autonomous_survey", "cites"),
    ("metagpt", "camel", "cites"),
    ("metagpt", "chatdev", "cites"),
    ("metagpt", "agentverse", "cites"),
    ("metagpt", "generative_agents", "cites"),
    ("metagpt", "debate", "cites"),
    ("chatdev", "camel", "cites"),
    ("chatdev", "metagpt", "cites"),
    ("chatdev", "generative_agents", "cites"),
    ("agentverse", "camel", "cites"),
    ("agentverse", "chatdev", "cites"),
    ("agentverse", "generative_agents", "cites"),
    ("agentverse", "debate", "cites"),
    ("autoagents", "camel", "cites"),
    ("autoagents", "metagpt", "cites"),
    ("autoagents", "auto_gen", "cites"),
    ("autoagents", "agentverse", "cites"),
    ("autoagents", "generative_agents", "cites"),
    ("autoagents", "spp", "cites"),
    ("agents_framework", "camel", "extends"),
    ("agents_framework", "chatdev", "cites"),
    ("agents_framework", "metagpt", "cites"),
    ("agents_framework", "generative_agents", "cites"),
    ("agents_framework", "comm_learning", "cites"),
    ("collab_llm", "camel", "cites"),
    ("collab_llm", "generative_agents", "cites"),
    ("social_psych", "debate", "cites"),
    ("social_psych", "camel", "cites"),
    ("social_psych", "collab_llm", "cites"),
    ("social_psych", "generative_agents", "cites"),
    ("spp", "debate", "cites"),
    ("spp", "camel", "cites"),
    ("spp", "generative_agents", "cites"),
    ("dylan", "debate", "cites"),
    ("dylan", "camel", "cites"),
    ("dylan", "auto_gen", "cites"),
    ("dylan", "agentverse", "cites"),
    ("dylan", "metagpt", "cites"),
    ("mas_survey", "collab_llm", "cites"),
    ("mas_survey", "generative_agents", "cites"),
    ("mas_survey", "camel", "cites"),
    ("mas_survey", "debate", "cites"),
    ("mas_survey", "got", "cites"),
    ("rise_survey", "generative_agents", "cites"),
    ("rise_survey", "camel", "cites"),
    ("rise_survey", "chatdev", "cites"),
    ("rise_survey", "metagpt", "cites"),
    ("rise_survey", "debate", "cites"),
    ("autonomous_survey", "generative_agents", "cites"),
    ("autonomous_survey", "camel", "cites"),
    ("autonomous_survey", "chatdev", "cites"),
    ("autonomous_survey", "metagpt", "cites"),
    ("agentbench", "generative_agents", "cites"),
    ("marl_survey", "comm_learning", "cites"),
    ("smac", "comm_learning", "related_to"),
    ("got", "debate", "related_to"),
    ("camel", "generative_agents", "related_to"),
    ("agents_framework", "agentverse", "cites"),
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
    ("conversation_programming", "agent_communication", "example_of"),
    ("inception_prompting", "role_playing", "example_of"),
    ("role_playing", "agent_roles", "example_of"),
    ("sop_workflows", "agent_roles", "example_of"),
    ("structured_communication", "agent_communication", "example_of"),
    ("multi_persona_prompting", "role_playing", "related_to"),
    ("executable_feedback", "hallucination_mitigation", "example_of"),
    ("multiagent_debate", "hallucination_mitigation", "example_of"),
    ("structured_communication", "hallucination_mitigation", "example_of"),
    ("memory_stream", "agent_memory", "example_of"),
    ("emergent_communication", "agent_communication", "example_of"),
    ("ctde", "marl", "example_of"),
    ("value_decomposition", "marl", "example_of"),
    ("value_decomposition", "ctde", "uses"),
    ("game_theory_mas", "marl", "related_to"),
    ("agent_architectures", "multi_agent_llm_systems", "part_of"),
    ("tool_use", "agent_architectures", "part_of"),
    ("planning", "agent_architectures", "part_of"),
    ("agent_memory", "agent_architectures", "part_of"),
    ("simulated_societies", "emergent_collaboration", "enables"),
    ("graph_based_reasoning", "planning", "related_to"),
]
