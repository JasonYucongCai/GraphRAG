# Information Process Protocol — Version 0.2.8

**Document Status:** Formal Specification  
**Version:** 0.2.8  
**Date:** 2026-08-06  
**Schema URI:** `https://ipp-spec.org/v0.2.8/schema.json`

## Abstract

The Information Process Protocol (IPP) treats every computational component — LLMs, agents, deterministic scripts, neural networks, and human experts — as interchangeable information-processing nodes with standardized input/output contracts. A single IPP Json File declares one or more independent channels, each a complete object-executor pair. An optional internal edge topology specifies how channels within the same node are directionally connected, enabling the specification of complete intra-node information processing pipelines. External topology is declared per-channel as a capability space and resolved at construction time against the live graph context.

---

## 1. Architectural Model

### 1.1 Constituent Separation

IPP v0.2.8 partitions the protocol into two orthogonal constituents, $\mathfrak{C} = \{\mathcal{F}, \mathcal{I}\}$, where:

| Constituent | Formal Nature | Cardinality | Denotation |
|:---|:---|:---|:---|
| $\mathcal{F}$ — **IPP Json File** | Static, declarative specification | $|\mathcal{F}| = 1$ per node | The formal definition of a single information-processing locus with $n \geq 1$ channels and an optional internal topology |
| $\mathcal{I}$ — **IPP Interface** | Dynamic, procedural realization | $|\mathcal{I}| = 2n + 1$ runtime peers | The runtime instantiation: $\mathcal{I} = \{\Gamma\} \cup \{\Omega_1, \ldots, \Omega_n\} \cup \{\Xi_1, \ldots, \Xi_n\}$ |

where $n = |\mathcal{F}.\text{channels}|$ is the number of channels declared in the Json File.

**Definition 1 (Runtime Peer Set).** The IPP Interface $\mathcal{I}$ consists of one autonomous Constructor and $n$ channel pairs:
- $\Gamma$ — the **IPP Constructor** (Independent Agent) — exactly one per node
- $\Omega_k$ — the **IPP Object for channel $k$** (Node, $k = 1 \ldots n$)
- $\Xi_k$ — the **IPP Executor for channel $k$** (Edge Connector / Runtime Enforcer, $k = 1 \ldots n$)

Each channel $k$ inherits its specification from the $k$-th element of $\mathcal{F}.\text{channels}$.

**Core Design Invariant.** $\Gamma$ is not structurally coupled to $\mathcal{F}$. $\Gamma$ may be realized as any autonomous agent $\mathcal{A}$ (an LLM, a code-generation system, a human operator, or a pure function) satisfying the construction protocol of §8.

After construction, $\Gamma$ is dormant (Lemma 1) but remains *recallable*: $\forall k, \forall t > t_{\text{construct}}, \; \Omega_k \rightsquigarrow \Gamma \lor \Xi_k \rightsquigarrow \Gamma$ — and $\Xi_k \rightsquigarrow \Gamma$ may be invoked for per-channel topology re-specification (re-wiring), or for internal topology re-specification.

### 1.2 Multi-Channel Principle

A single IPP node may process multiple, **heterogeneous** information flows simultaneously. Each channel is a logically independent information pipeline — it has its own input Port, process description, output Port, guardrail configuration, and edge capability space. Channels within the same node are structurally independent (§6.1). A node with $n = 1$ channel is equivalent to a single-channel deployment and remains the simplest valid configuration.

### 1.3 Internal Edge Topology

Channels within the same node may be **directionally connected** via internal edges. An internal edge routes data from the output port of one channel to the input port of another channel within the same node. This enables the specification of complete intra-node processing pipelines without requiring external routing infrastructure.

**Definition 17 (Internal Edge).** An *internal edge* is a 4-tuple:

$$e_{\text{int}} := (s, t, \mu, \theta)$$

where:
- $s = (c_s, p_s)$ — the **source endpoint**: a channel identifier $c_s$ and port $p_s \in \{\text{input}, \text{output}\}$. The source port must be `output` — internal edges originate at the output of a channel.
- $t = (c_t, p_t)$ — the **target endpoint**: a channel identifier $c_t$ and port $p_t$. The target port must be `input` — internal edges terminate at the input of a channel.
- $\mu \in \{\text{blocking}, \text{non\_blocking}, \text{callback}\}$ — the **flow control mode** (Definition 18)
- $\theta \in \mathbb{N}^+ \cup \{\infty\}$ — the **timeout** in milliseconds. Enforced only when $\mu = \text{blocking}$; ignored for `non_blocking` and `callback` modes.

**Constraints:**
1. $c_s \neq c_t$ — an internal edge must connect two *distinct* channels.
2. Both $c_s$ and $c_t$ must reference channel identifiers declared in $\mathcal{F}.\text{channels}$.

**Definition 18 (Flow Control Modes).**

| Mode | Semantics |
|:---|:---|
| **`blocking`** | The source executor suspends after dispatching the payload on the internal edge. It resumes when the target executor signals completion, or on timeout. This is the "request-response" pattern. |
| **`non_blocking`** | The source executor dispatches the payload and continues immediately. The target processes asynchronously. No completion signal is expected. |
| **`callback`** | The source executor dispatches the payload with a callback reference. The target invokes the callback upon completion, routing the result to a specified return port of the source channel. |

**Internal Topology as a Port-Level DAG.** The set of internal edges must form a **directed acyclic graph (DAG)**. The vertices of this graph are **ports**, not channels:

$$V_{\text{int}} := \{\, (c, p) \mid c \in \{\, \text{channels}.\text{channel\_id} \,\}, \; p \in \{\text{input}, \text{output}\} \,\}$$

$$G_{\text{int}} := (V_{\text{int}}, \mathcal{E}_{\text{int}})$$

An internal edge $e = ((c_s, \text{output}), (c_t, \text{input}), \mu, \theta)$ is a directed edge from vertex $(c_s, \text{output})$ to vertex $(c_t, \text{input})$. $G_{\text{int}}$ must be acyclic — no directed path may lead from a port back to itself.

**Why port-level vertices.** Data flows through a channel's handler $\mathcal{H}_k$ between its input and output ports. The handler is outside $G_{\text{int}}$ — it is the Object's computation, not an edge declaration. Two internal edges $(c_1, \text{output}) \to (c_2, \text{input})$ and $(c_2, \text{output}) \to (c_1, \text{input})$ do NOT form a cycle in $G_{\text{int}}$ because there is no edge from $(c_2, \text{input})$ to $(c_2, \text{output})$ — that path passes through $\mathcal{H}_{c_2}$, which is outside the declared topology. This pattern (called a *pipeline loop*) is a valid and common design for two-channel request-response architectures. A true structural cycle — where $(c, \text{output})$ reaches $(c, \text{input})$ through internal edges alone, without passing through any handler — is prohibited and will be rejected by the Constructor at validation time (Theorem 9, Invariant I15).

**Relationship to external topology.** Internal edges are *declarative* — specified directly in the Json File by the node author, because the internal channel structure is part of the node's design. External edges remain *capability-space-based* — resolved against the graph context $\mathcal{G}$ at construction time. The responsibility split:

| Edge Type | Who specifies | Where specified | Resolution |
|:---|:---|:---|:---|
| **Internal edges** ($\mathcal{E}_{\text{int}}$) | The node author | $\mathcal{F}.\text{internal\_topology}$ | Declared directly (part of node design) |
| **External edges** ($\tau^*_k$) | The Constructor $\Gamma$ | Resolved from $\mathcal{K}_{\tau,k} \times \mathcal{G}$ | Constructor-time resolution |

### 1.4 Topology Decoupling Principle

The Json File declares, **per channel**, **which external edges are possible** via the edge capability space $\mathcal{K}_{\tau,k}$. External concrete topology is Constructor-resolved. Internal topology is declared directly as a set of edges. Neither specifies concrete external wiring in the file.

### 1.5 Architectural Diagram

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 IPP v0.2.8 — Formal Architecture                                  │
│                                                                                                  │
│  ┌────────────────────────────────────────────────┐      ┌───────────────────────────────────┐  │
│  │   F — IPP Json File                            │      │  Γ — IPP Constructor               │  │
│  │   (declarative specification)                   │      │  (Independent Agent)               │  │
│  │                                                │      │                                    │  │
│  │  channels: [channel₁, ..., channelₙ]           │      │  Γ : F × 𝒢 → ({Ω_k}, {Ξ_k[τ*_k]},  │  │
│  │  internal_topology?: { edges: [e₁, ..., eₘ] }  │───►  │            E_int)                   │  │
│  │                                                │      │                                    │  │
│  └────────────────────────────────────────────────┘      │  For each channel k = 1..n:        │  │
│                                                          │    Step 5: RESOLVE external τ*_k    │  │
│  ┌────────────────────────────────────────────────┐      │  Step 6: WIRE internal edges        │  │
│  │  𝒢 — GRAPH CONTEXT (external)                   │───►  │    DAG validation, build routing     │  │
│  │  Registry N, candidates, supervisor intent      │      └──────────┬──────────┬──────────────┘  │
│  └────────────────────────────────────────────────┘             │          │                    │
│                                                        construct_Ω_k  construct_Ξ_k             │
│                                                                 │          ▼                    │
│                                                         ┌───────▼──────┐ ┌──────────────────┐   │
│                                                         │  Ω_k — Obj   │ │  Ξ_k — Executor  │   │
│                                                         │  · H_k       │ │  · τ*_k          │   │
│                                                         │  · ports_k   │ │  · I_out_k       │   │
│                                                         │  · γ_Ωk↝Γ    │ │  · I_in_k        │   │
│                                                         └──────────────┘ │  · γ_Ξk↝Γ        │   │
│                                                                          └──────────────────┘   │
│  All 2n+1 peers pairwise independent (save Ω_k↔Ξ_k cooperation within channel)                  │
│  Internal edges carry data; do not share state                                                  │
│  Re-wiring (external): Ξ_k ──γ_Ξk──► Γ(𝒢'_k)                                                   │
│  Internal re-spec:      Γ( F[internal_topology'] )                                              │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. The IPP Json File — Formal Syntax and Semantics

### 2.1 Abstract Grammar

Let $\Sigma_{\text{IPP}}$ denote the formal alphabet of IPP v0.2.8. A well-formed IPP Json File $\mathcal{F}$ is a term satisfying:

```
F ::= { "$schema": S, "ipp_version": V, "node_id": N,
        "channels": [channel₁, ..., channelₙ],
        "internal_topology"?: InternalTopology }
S ::= "https://ipp-spec.org/v0.2.8/schema.json"
V ::= "0.2.8"
N ::= <string> — globally unique node identifier within the IPP topology
n ≥ 1 — at least one channel required
? denotes optional — internal_topology may be omitted (equivalent to no internal edges)

channel ::= { "channel_id": C, "ipp_object": ω_decl, "ipp_executor": ξ_decl }
C ::= <string> — unique within this file; identifies the channel for routing, recall, and provenance

ω_decl ::= { "input": Port, "process": ProcessSpec, "output": Port }
ξ_decl ::= { "integrity": IntegritySpec, "policy": PolicySpec,
             "provenance": ProvenanceSpec, "error_handling": ErrorSpec,
             "edge_capabilities": CapabilitySpace }

InternalTopology ::= { "edges": [InternalEdge₁, ..., InternalEdgeₘ] }
InternalEdge ::= { "from": Endpoint, "to": Endpoint,
                   "mode": FlowMode, "timeout_ms"?: integer }
Endpoint ::= { "channel_id": C, "port": "input" | "output" }
FlowMode ::= "blocking" | "non_blocking" | "callback"
m ≥ 0 — zero or more internal edges
```

**Internal edge validity rules:**
| Rule | Statement |
|:---|:---|
| **R1 (Direction)** | $\forall e \in \mathcal{E}_{\text{int}}: e.\text{from}.\text{port} = \text{"output"} \land e.\text{to}.\text{port} = \text{"input"}$ |
| **R2 (Distinct channels)** | $\forall e \in \mathcal{E}_{\text{int}}: e.\text{from}.\text{channel\_id} \neq e.\text{to}.\text{channel\_id}$ |
| **R3 (Valid references)** | Every `channel_id` in $\mathcal{E}_{\text{int}}$ must appear in $\mathcal{F}.\text{channels}$ |
| **R4 (Acyclicity)** | $G_{\text{int}} = (V_{\text{int}}, \mathcal{E}_{\text{int}})$ is a DAG (see §1.3) |

**Migration.** Files from earlier IPP versions without `internal_topology` are valid v0.2.8 files. Files with a single top-level `ipp_object`/`ipp_executor` pair (v0.2.6 and earlier) migrate to a single-element `channels` array with `channel_id: "default"`.

### 2.2 The Port

**Definition 2 (Port).** A *Port* $\Pi$ is a structural contract at an information boundary, defined as the Cartesian product of three orthogonal sub-structures:

$$\Pi := \Phi \times A \times T$$

where:
- $\Phi$ — the **core flow** (data plane): $\Phi = \Lambda_1 \times \Lambda_2 \times \Lambda_3$, comprising Payload ($\Lambda_1$), Metadata ($\Lambda_2$), and Control/Status ($\Lambda_3$)
- $A$ — the **accommodation** (operational metadata plane): $A = \Lambda_4 \times \Lambda_7$, comprising Routing/Addressing ($\Lambda_4$) and Policies/QoS ($\Lambda_7$)
- $T$ — the **template** (structural contract): $T = \Lambda_6$, the Schema/Template layer

The orthogonality property $\Pi \cong \Phi \times A \times T$ guarantees that each factor can evolve independently. Each channel $k$ has its own input Port $\Pi_{\text{in},k}$ and output Port $\Pi_{\text{out},k}$. A port may receive data from both external edges (via the Executor's dispatch) and internal edges (from another channel within the same node). The provenance of each input is recorded in $\Lambda_3$ as `source: "external" | "internal"` with the source qualifier.

### 2.3 The Ten-Layer Taxonomy

An information unit spans up to ten orthogonal layers ($\Lambda_1$–$\Lambda_{10}$), each answering a distinct question:

| Layer | Name | Answers | Example |
|:---|:---|:---|:---|
| $\Lambda_1$ | Payload | What is the content? | Image pixels, text prompt, sensor reading |
| $\Lambda_2$ | Metadata | What format? | `content_type`, `created_at`, version |
| $\Lambda_3$ | Control/Status | Where in the pipeline? | `status: "processing"`, `session_id`, `channel_id`, `source: "internal"|"external"` |
| $\Lambda_4$ | Routing/Addressing | Where is it going? | `from: (node_A, ch1)`, `to: (node_B, ch2)`, `internal_to: ch2` |
| $\Lambda_5$ | Integrity/Verification | Is it intact? | checksum, digital signature, hash |
| $\Lambda_6$ | Schema/Template | What structure? | JSON Schema, validation rules |
| $\Lambda_7$ | Policies/QoS | Under what constraints? | `max_cost`, `timeout`, `requires_hipaa` |
| $\Lambda_8$ | Provenance/Audit | What touched it? | `processed_by`, `audit_log`, `channel_id`, internal edge traversal records |
| $\Lambda_9$ | Error/Fallback | What went wrong? | `error_code`, `fallback_to`, internal edge timeout |
| $\Lambda_{10}$ | Edge/Topology | How is it connected? | External upstream/downstream sets + internal edge inventory |

**Layer-to-Port Mapping:**

| Port Factor | Layers Contained | Semantic Domain |
|:---|:---|:---|
| $\Phi$ (core_flow) | $\Lambda_1, \Lambda_2, \Lambda_3$ | Data plane: content, format, pipeline state |
| $A$ (accommodation) | $\Lambda_4, \Lambda_7$ | Operational metadata: identity, routing, constraints |
| $T$ (template) | $\Lambda_6$ | Structural contract: schema, validation rules |

### 2.4 The Edge Capability Space

**Definition 11 (Edge Capability Space).** The *edge capability space* of channel $k$ is the 4-tuple:

$$\mathcal{K}_{\tau,k} := (C_{U,k}, C_{D,k}, \mathcal{R}_k, \mathcal{C}_k)$$

where:
- $C_{U,k}$ — admissible **upstream** edge classes: compatibility contracts describing which kinds of predecessor nodes (and their channels) may feed this channel. Each class has a node class, output logical type, compatibility mode (`exact` / `convertible` / `any`), and an edge-count range $[m_U, M_U]$.
- $C_{D,k}$ — admissible **downstream** edge classes: which kinds of successor nodes (and their channels) may be fed, each with a range $[m_D, M_D]$.
- $\mathcal{R}_k$ — supported **routing modes**: $\mathcal{R}_k \subseteq \{\text{unicast}, \text{multicast}, \text{broadcast}, \text{anycast}, \text{reduce}\}$.
- $\mathcal{C}_k$ — the **constraint envelope**: maximum parallel edges, acknowledgment capability (`optional` / `required` / `unsupported`), supported backpressure modes (`drop` / `buffer` / `block`), and resolution policy (`constructor_resolved` / `supervisor_guided` / `open`).

The space of topologies admitted for channel $k$: $\mathcal{T}(\mathcal{K}_{\tau,k}) := \{\, \tau_k \;|\; \tau_k \text{ conforms to } \mathcal{K}_{\tau,k} \,\}$. Each channel's capability space is resolved independently by the Constructor. This declares possible **external** edges only; internal edges are declared separately in $\mathcal{F}.\text{internal\_topology}$.

### 2.5 Internal Topology — Formal Definition

**Definition 19 (Internal Topology).** The *internal topology* of a node is the set of internal edges $\mathcal{E}_{\text{int}} = \{e_{\text{int},1}, \ldots, e_{\text{int},m}\}$ together with the implicit port structure of all declared channels. The internal topology is the directed graph $G_{\text{int}} = (V_{\text{int}}, \mathcal{E}_{\text{int}})$ with port-level vertices as defined in §1.3.

**Example.** Consider a node with two channels `"ch_A"` and `"ch_B"` that form a request-response pipeline:

```json
"internal_topology": {
  "edges": [
    {
      "from": { "channel_id": "ch_A", "port": "output" },
      "to":   { "channel_id": "ch_B", "port": "input" },
      "mode": "blocking",
      "timeout_ms": 30000
    },
    {
      "from": { "channel_id": "ch_B", "port": "output" },
      "to":   { "channel_id": "ch_A", "port": "input" },
      "mode": "blocking",
      "timeout_ms": 30000
    }
  ]
}
```

Vertices of $G_{\text{int}}$: $(A, \text{input}), (A, \text{output}), (B, \text{input}), (B, \text{output})$. Edges: $(A, \text{output}) \to (B, \text{input})$ and $(B, \text{output}) \to (A, \text{input})$. No cycle exists — the path from $(B, \text{input})$ to $(B, \text{output})$ passes through $\mathcal{H}_B$, which is outside $G_{\text{int}}$. This is a valid DAG.

---

## 3. The IPP Interface — Formal Semantics

### 3.1 Structural Independence

**Definition 3 (Structural Independence).** Two runtime entities $E_1, E_2 \in \mathcal{I}$ are *structurally independent*, denoted $E_1 \bot E_2$, iff they have disjoint lifecycles, disjoint state spaces, and no inter-state function necessarily invoked during normal operation.

**Theorem 1a (Within-Channel Object-Executor Independence).** For each channel $k$: $\Omega_k \bot \Xi_k$.

**Theorem 1b (Cross-Channel Object Independence).** $\forall i \neq j$: $\Omega_i \bot \Omega_j$. Each $\Omega_i$ has its own handler $\mathcal{H}_i$, ports $\Pi_{\text{in},i}, \Pi_{\text{out},i}$, and state $\sigma_{\Omega,i}$. Channels share no state, lifecycle transitions, or inter-state functions.

**Theorem 1c (Cross-Channel Executor Independence).** $\forall i \neq j$: $\Xi_i \bot \Xi_j$. Additionally, $\Omega_i \bot \Xi_j$ for $i \neq j$, since $\Omega_i$ operates on channel-$i$ payloads and $\Xi_j$ enforces channel-$j$ guardrails — disjoint type signatures.

**Theorem 1d (Internal Edge Non-Violation of Independence).** For any $i \neq j$ connected by an internal edge: $\Omega_i \bot \Omega_j$ is not violated. The internal edge carries a copy of the payload from $\Omega_i$'s output to $\Omega_j$'s input via the executors' routing; no state is shared. $\Omega_j$ processes the payload independently using $\mathcal{H}_j$ and $\sigma_{\Omega,j}$.

**Corollary (Universal Pairwise Independence).** $\forall E_a, E_b \in \mathcal{I}, E_a \neq E_b \implies E_a \bot E_b$, with the sole exception that $\Omega_k$ and $\Xi_k$ cooperate during execution (the Executor wraps the Object's handler in the guardrail envelope), but remain structurally independent per Theorem 1a.

### 3.2 The Graph Context

**Definition 12 (Graph Context).** The *graph context* $\mathcal{G}$ is the external, deployment-specific state consulted by the Constructor for **external** topology resolution:

$$\mathcal{G} := (\mathcal{N}, \mathcal{E}_{\text{cand}}, \mathcal{P}_{\text{sup}})$$

where:
- $\mathcal{N}$ — the **registry**: the set of available nodes with their channel lists and per-channel capability spaces
- $\mathcal{E}_{\text{cand}}$ — the **candidate edge set**: all $((n_i, c_a), (n_j, c_b))$ (node, channel) pairs whose capability spaces are mutually compatible
- $\mathcal{P}_{\text{sup}}$ — the **supervisor intent and edge policies**: deployment goals, wiring preferences, cost/latency/security guidance

$\mathcal{G}$ is *not* part of $\mathcal{F}$; it varies by deployment. This is what makes external topology un-declarable in a static file (Theorem 6, §8.4).

### 3.3 Topology Resolution

**Definition 13 (Topology Resolution).** For channel $k$: $\text{resolve}_k: \mathcal{K}_{\tau,k} \times \mathcal{G} \to \mathcal{T}(\mathcal{K}_{\tau,k})$. The 5-step procedure:

1. **Read** $\mathcal{K}_{\tau,k}$ from the channel's executor declaration.
2. **Query** $\mathcal{G}$ for candidate partners compatible with $C_{U,k}$ and $C_{D,k}$.
3. **Enumerate** the admissible wiring set $\mathcal{W}_k \subseteq \mathcal{T}(\mathcal{K}_{\tau,k})$.
4. **Select** $\tau^*_k \in \mathcal{W}_k$ — or the *open-port topology* if no compatible partner exists — guided by $\mathcal{P}_{\text{sup}}$ and $\mathcal{C}_k$.
5. **Build** $\tau^*_k$ into $\Xi_k$ as built-in edge state.

Resolution of different channels is independent.

### 3.4 The Realized Topology

**Definition 14 (Realized Topology).** The *realized topology* for channel $k$ is:

$$\tau^*_k := (U^*_k, D^*_k, R^*_k, C^*_k, I^{\text{out}}_k, I^{\text{in}}_k)$$

where:
- $U^*_k, D^*_k$ — instantiated external upstream and downstream partners (qualified by $(node, channel)$ pairs)
- $R^*_k: \text{Output} \times \text{Context} \to \mathcal{P}(D^*_k \cup I^{\text{out}}_k)$ — the routing function, covering both external and internal destinations
- $C^*_k$ — concrete edge constraints (parallel budget, acknowledgment, backpressure)
- $I^{\text{out}}_k \subseteq \mathcal{E}_{\text{int}}$ — outgoing internal edges (routed by this executor)
- $I^{\text{in}}_k \subseteq \mathcal{E}_{\text{int}}$ — incoming internal edges (delivering to this channel's input)

All components are selected by $\Gamma$ at construction and conform to $\mathcal{K}_{\tau,k}$ (Theorem 7). $\tau^*_k$ is part of $\Xi_k$'s constructed state and is never read from any file at runtime. When the graph changes, $\Xi_k$ recalls $\Gamma$ for re-resolution — the Json File is never edited for a wiring change.

### 3.5 Entity Definitions

**Definition 4 (IPP Constructor — $\Gamma$).** $\Gamma$ reads $\mathcal{F} \times \mathcal{G}$ and produces:

$$\Gamma \in \mathcal{A} \quad \text{s.t.} \quad \Gamma \Vdash \mathcal{F} \times \mathcal{G} \leadsto (\{\, (\Omega_k, \Xi_k[\tau^*_k]) \mid k = 1 \ldots n \,\}, \mathcal{E}_{\text{int}})$$

The Constructor produces the set of channel pairs and the wired internal edge set.

**Definition 5 (IPP Object — $\Omega_k$).** $\Omega_k := (\Pi_{\text{in},k}, \mathcal{H}_k, \Pi_{\text{out},k}, \sigma_{\Omega,k}, \gamma_{\Omega,k})$. The Object is unaware of whether its inputs arrive from external or internal sources — this is the Executor's concern. Different channels may have entirely different handler implementations (e.g., a CNN, an LLM call, a deterministic script).

**Definition 6 (IPP Executor — $\Xi_k$).** $\Xi_k := (\iota_k, \pi_k, \rho_k, \varepsilon_k, \tau^*_k, \gamma_{\Xi,k})$, where $\tau^*_k$ now contains the extended topology (Definition 14) with $I^{\text{out}}_k$ and $I^{\text{in}}_k$. Each channel has independent guardrails, audit log, and recall reference.

---

## 4. IPP Object — Formal Definition

### 4.1 Type Signature

The IPP Object for channel $k$ is an element of the type:

$$\Omega_k : \Pi_{\text{in},k} \times \mathcal{H}_k \times \Pi_{\text{out},k} \times \Sigma_{\Omega,k} \to \text{Payload} \times \Sigma_{\Omega,k}'$$

where $\Sigma_{\Omega,k}$ is the state space and $\Sigma_{\Omega,k}'$ is the post-execution state.

| Component | Source | Formal Type |
|:---|:---|:---|
| $\Pi_{\text{in},k}$ | $\mathcal{F}.\text{channels}[k].\text{ipp\_object}.\text{input}$ | $\text{Port}$ (Definition 2) |
| $\mathcal{H}_k$ | $\mathcal{F}.\text{channels}[k].\text{ipp\_object}.\text{process}$ + bound handler | $\text{Payload} \times \text{Context} \to \text{Payload}$ |
| $\Pi_{\text{out},k}$ | $\mathcal{F}.\text{channels}[k].\text{ipp\_object}.\text{output}$ | $\text{Port}$ (Definition 2) |
| $\sigma_{\Omega,k}$ | Initialized at construction | $\{\text{counters}, \text{caches}, \text{learned\_params}, \text{session\_data}\}$ |
| $\gamma_{\Omega,k}$ | Bound by $\Gamma$ at construction | $\text{Ref}(\Gamma)$ |

### 4.2 Axiomatic Specification

**Axiom O1 (Input Conformance).** $\forall \text{input} \in \text{Domain}(\mathcal{H}_k), \; \text{input} \vDash \Pi_{\text{in},k}.\text{schema}$.

**Axiom O2 (Output Conformance).** $\forall \text{output} \in \text{Range}(\mathcal{H}_k), \; \text{output} \vDash \Pi_{\text{out},k}.\text{schema}$.

**Axiom O3 (State Preservation).** $\sigma_{\Omega,k}^{(t+1)} = \mathcal{H}_k(\text{input}^{(t)}, \sigma_{\Omega,k}^{(t)})|_{\text{state}}$.

**Axiom O4 (Recall Capability).** $\Omega_k$ may invoke $\gamma_{\Omega,k}$ at any time $t$ to request re-construction with a modified channel-$k$ declaration.

**Axiom O5 (Cross-Channel State Isolation).** $\forall i \neq j, \; \sigma_{\Omega,i} \cap \sigma_{\Omega,j} = \varnothing$. No channel object may read or write another channel's state. Internal edges carry payloads, not state (Theorem 1d).

### 4.3 Lifecycle Automaton

Each $\Omega_k$ is governed by an independent finite state machine $\mathcal{M}_{\Omega,k} = (Q_{\Omega}, \Sigma_{\Omega}^{\text{event}}, \delta_{\Omega}, q_0, F_{\Omega})$ with $Q_{\Omega} = \{\text{unborn}, \text{active}, \text{improving}, \text{draining}, \text{retired}\}$ and $q_0 = \text{unborn}$:

| Current State | Event | Next State | Side Effect |
|:---|:---|:---|:---|
| unborn | $\text{construct}(\Gamma, \omega_{\text{decl},k})$ | active | $\Omega_k$ initialized; $\gamma_{\Omega,k}$ bound |
| active | $\text{execute}(\text{input})$ | active | $\mathcal{H}_k(\text{input})$ executed; $\sigma_{\Omega,k}$ updated |
| active | $\text{recall}(\gamma_{\Omega,k}, \omega_{\text{decl},k}')$ | improving | $\Gamma$ invoked for re-construction |
| improving | $\text{swap}(\Omega_k')$ | active | Atomic replacement: $\Omega_k \leftarrow \Omega_k'$ |
| active | $\text{drain}$ | draining | No new executions; in-flight completions allowed |
| draining | $\text{all\_flights\_drained}$ | retired | $\Omega_k$ destroyed |
| active | $\text{destroy}$ | retired | Immediate retirement (emergency) |

Channel lifecycles are independent — $\Omega_1$ may be `active` while $\Omega_2$ is `draining`.

---

## 5. IPP Executor — Formal Definition

### 5.1 Type Signature

$$\Xi_k : \Omega_k \times \text{Payload} \times \text{Context} \to \text{GuardedOutput} \times \text{ExecutionRecord}$$

### 5.2 Compositional Semantics

| Component | Source | Formal Type |
|:---|:---|:---|
| $\iota_k$ | $\mathcal{F}.\text{channels}[k].\text{ipp\_executor}.\text{integrity}$ | $\text{Payload} \to \{\text{accept}, \text{reject}\} \times \text{Checksum}$ |
| $\pi_k$ | $\mathcal{F}.\text{channels}[k].\text{ipp\_executor}.\text{policy}$ | $\text{Context} \to \{\text{allow}, \text{deny}\} \times \text{PolicyReport}$ |
| $\rho_k$ | $\mathcal{F}.\text{channels}[k].\text{ipp\_executor}.\text{provenance}$ | $\text{ExecutionRecord} \to \text{AuditLog}_k \to \text{AuditLog}_k'$ |
| $\varepsilon_k$ | $\mathcal{F}.\text{channels}[k].\text{ipp\_executor}.\text{error\_handling}$ | $\text{Error} \to \{\text{retry}, \text{fallback}, \text{escalate}\} \times \text{ErrorReport}$ |
| $\tau^*_k$ | $\Gamma$'s resolution (external + internal) | $\text{Output} \to \mathcal{P}(D^*_k \cup I^{\text{out}}_k) \times \text{RoutingDecision}$ |
| $\gamma_{\Xi,k}$ | Bound by $\Gamma$ at construction | $\text{Ref}(\Gamma)$ — recall, including internal re-wiring |

### 5.3 Built-in Edge Topology — Runtime Roles

| Role | Runtime behavior |
|:---|:---|
| **Ownership** | $\tau^*_k$ is state of $\Xi_k$ only (Axiom X6), including $I^{\text{out}}_k, I^{\text{in}}_k$ |
| **External Dispatch** | $R^*_k(p', c)$ routes to external $D^*_{k,\text{target}}$ |
| **Internal Dispatch** | $R^*_k(p', c)$ routes to internal targets $I^{\text{out}}_k$; enforces flow control mode |
| **Backpressure & Ack** | $C^*_k$ enforced per channel; internal blocking edges await completion signals |
| **Conformance** | Refuse dispatch outside $\mathcal{K}_{\tau,k} \cup I^{\text{out}}_k$ (Axiom X5) |

### 5.4 Axiomatic Specification

**Axiom X1 (Guardrail Completeness).** $\forall$ execution paths through $\Xi_k$, the sequence of operations is strictly:

$$\iota_{\text{pre},k} \to \pi_k \to [\Omega_k.\text{execute}] \to \iota_{\text{post},k} \to \rho_k \to \tau^*_k$$

There is no bypass path.

**Axiom X2 (Fail-Safe).** $\Xi_k$ never produces an unhandled exception. For any fault $f$: $\Xi_k(f) \in \{\text{retry}(n), \text{fallback}(D_{\text{fallback}}), \text{escalate}(\text{level})\}$ where $D_{\text{fallback}} \subseteq D^*_k \cup \{\text{human\_review}\}$.

**Axiom X3 (Audit Immutability).** If provenance audit level is `full`, every invocation produces an append-only, hash-chained $\text{ExecutionRecord}$: $\text{hash}(\text{Record}_n) = H(\text{Record}_n.\text{data} \parallel \text{hash}(\text{Record}_{n-1}))$.

**Axiom X4 (Recall Capability).** $\Xi_k$ may invoke $\gamma_{\Xi,k}$ to request re-construction with a modified executor declaration.

**Axiom X5 (Topology Conformance).** $D^*_{k,\text{target}} \subseteq D^*_k$, and every edge in $U^*_k \cup D^*_k$ conforms to $\mathcal{K}_{\tau,k}$. The Executor never uses an edge the capability space does not admit.

**Axiom X6 (No In-Band Topology Mutation).** $\tau^*_k$ is immutable during execution. $U^*_k, D^*_k, R^*_k, C^*_k, I^{\text{out}}_k, I^{\text{in}}_k$ change only through $\gamma_{\Xi,k} \rightsquigarrow \Gamma$ (recall-based re-resolution).

**Axiom X7 (Cross-Channel Guardrail Isolation).** $\forall i \neq j$, guardrail execution of $\Xi_i$ does not depend on, block, or interfere with $\Xi_j$.

**Axiom X8 (Internal Edge Flow Control).** For each internal edge $e = (s, t, \mu, \theta) \in I^{\text{out}}_k$:
- $\mu = \text{blocking}$: the source executor $\Xi_k$ suspends after dispatch until it receives a `completion_signal` from $\Xi_t$ or until $\theta$ ms elapse (timeout → $\varepsilon_k$ fallback with error code `internal_timeout`).
- $\mu = \text{non\_blocking}$: dispatch and continue immediately; no completion signal. $\theta$ is ignored.
- $\mu = \text{callback}$: dispatch with a callback reference; the target executor invokes the callback upon completion, routing the result to the specified return port of the source channel. $\theta$ is ignored.

**Axiom X9 (Internal Edge Provenance).** Every traversal of an internal edge is recorded in the provenance logs of both the source and target executors, including: edge identifier, timestamp, payload hash, flow control mode, and completion status.

### 5.5 Operational Semantics — Guardrail Envelope

$$\displaylines{
\langle \Xi_k, \Omega_k, p, c \rangle \\
\quad \xrightarrow{\iota_{\text{pre},k}} \langle \Xi_k, \Omega_k, p, c \rangle_{\text{integrity}} \quad \text{if } \iota_k(p) = (\text{accept}, h_{\text{in}}) \\
\quad \xrightarrow{\pi_k} \langle \Xi_k, \Omega_k, p, c \rangle_{\text{policy}} \quad \text{if } \pi_k(c) = (\text{allow}, \_) \\
\quad \xrightarrow{\Omega_k.\text{execute}} \langle \Xi_k, \Omega_k, p', c \rangle_{\text{processed}} \quad \text{where } p' = \mathcal{H}_k(p, c) \\
\quad \xrightarrow{\iota_{\text{post},k}} \langle \Xi_k, \Omega_k, p', c \rangle_{\text{verified}} \quad \text{where } h_{\text{out}} = H(p') \\
\quad \xrightarrow{\rho_k} \langle \Xi_k, \Omega_k, (p', \text{record}), c \rangle_{\text{audited}} \\
\quad \xrightarrow{\tau^*_{k,\text{dispatch}}} \langle \Xi_k, \Omega_k, (p', \text{record}), D^*_{k,\text{target}} \cup I^{\text{out}}_{k,\text{target}} \rangle_{\text{dispatched}}
}$$

If any pre-condition step fails: $\langle \Xi_k, \Omega_k, p, c \rangle \xrightarrow{\text{guard\_fail}(f)} \langle \Xi_k, \varepsilon_k(f), \Omega_k, c \rangle_{\text{error}}$ (Axiom X2).

After dispatch, for blocking internal edges: $\langle \Xi_k, \ldots \rangle_{\text{dispatched}} \xrightarrow{\text{await\_internal}} \langle \Xi_k, \ldots \rangle_{\text{internal\_complete}} \lor \xrightarrow{\text{timeout}(\theta)} \langle \Xi_k, \varepsilon_k(\text{internal\_timeout}), \ldots \rangle_{\text{error}}$

### 5.6 Enforcement Domain Summary

| Domain | Formal Predicate | Pre-condition | Post-condition | Failure Mode |
|:---|:---|:---|:---|:---|
| $\iota_k$ (Integrity) | $\text{valid}(p)$ | $\text{valid}(p)$ | $h_{\text{out}} = H(p')$ | $\text{reject}(\text{corrupted})$ |
| $\pi_k$ (Policy) | $\text{admissible}(c)$ | $\text{admissible}(c)$ | Policy report appended | $\text{reject}(\text{policy\_violation})$ |
| $\rho_k$ (Provenance) | — (always) | — | Record appended (incl. internal edge traversals per X9) | $\text{flag}(\text{provenance\_gap})$ |
| $\varepsilon_k$ (Error) | — (always) | Fault detected | resolved or escalated | Escalation; new mode: `internal_timeout` |
| $\tau^*_k$ (Topology) | $\text{routable}$ | built-in | Dispatch per $R^*_k$; conformance per $\mathcal{K}_{\tau,k}$ and $\mathcal{E}_{\text{int}}$ | $\text{flag}(\text{misroute})$ or recall → re-resolve |

### 5.7 Guardrail Architecture

```
                         ┌─────────────────────────────────┐
   input ───────────────►│  ι_pre : Integrity Verification  │
   (external or internal)│  · checksum validation           │──► reject (ε: fallback)
                         │  · signature verification        │
                         │  · schema validation             │
                         └─────────────┬───────────────────┘
                                       │ accept
                         ┌─────────────▼───────────────────┐
                         │  π : Policy Evaluation           │──► reject (ε: retry/fallback)
                         │  · rate limit, cost cap, SLA    │
                         │  · security clearance            │
                         └─────────────┬───────────────────┘
                                       │ allow
                         ┌─────────────▼───────────────────┐
                         │  Ω_k : IPP Object (Node)        │
                         │  H_k(input) → output             │
                         │  σ_Ωk ← σ_Ωk'                   │
                         └─────────────┬───────────────────┘
                                       │
                         ┌─────────────▼───────────────────┐
                         │  ι_post : Output Integrity       │
                         │  · attach fresh checksum         │
                         └─────────────┬───────────────────┘
                                       │
                         ┌─────────────▼───────────────────┐
                         │  ρ : Provenance Recording        │──► flag (provenance_gap)
                         │  · hash-chain append             │
                         │  · record internal edge traversals│
                         └─────────────┬───────────────────┘
                                       │
                         ┌─────────────▼───────────────────┐
                         │  τ* : Edge Dispatch              │
                         │  · External: route to D*_target  │
                         │  · Internal: route to I_out      │
                         │  · Flow control (blocking/       │──► flag (misroute)
                         │    non_blocking/callback)        │
                         └─────────────┬───────────────────┘
                                       │
                              ┌────────┴────────┐
                              ▼                 ▼
                       external targets   internal targets
                              │                 │
                              │    ┌────────────┴────────────┐
                              │    │ non_blocking: fire & go │
                              │    │ blocking: await or τ    │
                              │    │ callback: invoke cb     │
                              │    └─────────────────────────┘
                              ▼
                           output
```

---

## 6. Object-Executor Independence

### 6.1 Strong Independence Theorem

**Theorem 2 (Strong Independence).** The runtime peers satisfy:

1. **Within-channel:** $\Omega_k \bot \Xi_k$ (Theorem 1a).
2. **Cross-channel objects:** $\Omega_i \bot \Omega_j$ for $i \neq j$ (Theorem 1b).
3. **Cross-channel executors:** $\Xi_i \bot \Xi_j$ for $i \neq j$ (Theorem 1c).
4. **Cross-type:** $\Omega_i \bot \Xi_j$ for $i \neq j$ (Theorem 1c).
5. **Internal edge non-violation:** Internal edges do not violate any of the above (Theorem 1d).

| Property | Cross-Channel Guarantee |
|:---|:---|
| **Testability** | Each channel $k$ is testable in complete isolation |
| **Replaceability** | $\text{swap}(\Omega_k, \Omega_k')$ affects only channel $k$ |
| **Concurrency** | Channels may execute simultaneously without locks, synchronization, or ordering constraints |
| **Internal edge isolation** | Internal edges carry payloads; no state is shared through them |

### 6.2 Constructor Dormancy

**Lemma 1 (Constructor Dormancy).** After construction, $\Gamma$ is not on any critical execution path for any channel: $\forall k, \forall t > t_0, \forall p, \; \text{execute}(\Omega_k, \Xi_k, p) \text{ does not invoke } \Gamma$.

### 6.3 Recall Mechanism & Re-wiring

**Definition 15 (Recall Relation).** For each channel $k$: $\Omega_k \rightsquigarrow \Gamma$ and $\Xi_k \rightsquigarrow \Gamma$ — entity $E_k$ recalls $\Gamma$ by invoking $\gamma_{E,k}$, passing a modified declaration $\delta'_k$ (and optionally a new graph context $\mathcal{G}'_k$), and receiving a re-constructed $E'_k$.

**Recall Modes:**

| Mode | Initiator | Scope | Result |
|:---|:---|:---|:---|
| **Object-initiated** | $\Omega_k$ via $\gamma_{\Omega,k}$ | Channel $k$ only | $\Omega_k'$ — hot-swap |
| **Executor-initiated** | $\Xi_k$ via $\gamma_{\Xi,k}$ | Channel $k$ only | $\Xi_k'$ — hot-swap |
| **Topology re-resolution** | $\Xi_k$ via $\gamma_{\Xi,k}$ | Channel $k$ only | $\tau^{*\prime}_k$ — external re-wire ($\mathcal{F}$ unchanged) |
| **Internal topology re-spec** | $\Gamma$ (any trigger) | All channels | $\mathcal{E}_{\text{int}}'$ — internal edges atomically re-wired |
| **Channel addition** | $\Gamma$ (external trigger) | New channel | $(\Omega_{n+1}, \Xi_{n+1})$ — hot-add; may update $\mathcal{E}_{\text{int}}$ |
| **Channel removal** | $\Gamma$ (external trigger) | Channel $k$ | Drain and destroy; remove all internal edges incident on $k$ |
| **Coordinated** | Multiple channels | Specified channels | Consistent multi-channel + internal topology swap |

---

## 7. Layer-to-Component Mapping

### 7.1 Formal Assignment

The ten-layer taxonomy $\Lambda = \{\Lambda_1, \ldots, \Lambda_{10}\}$ is partitioned per channel:

| Layer | Denotation | Declaration in $\mathcal{F}$ | Runtime Component |
|:---|:---|:---|:---|
| $\Lambda_1$ | Payload | `channels[k].ipp_object.input.Φ.payload` | $\Omega_k$ |
| $\Lambda_2$ | Metadata | `channels[k].ipp_object.input.Φ.metadata` | $\Omega_k$ |
| $\Lambda_3$ | Control/Status | `channels[k].ipp_object.input.Φ.control_status` (+ `source`, `source_channel_id`) | $\Omega_k$ |
| $\Lambda_4$ | Routing/Addressing | `channels[k].ipp_object.input.A.routing` (+ internal routing qualifiers) | $\Omega_k$ |
| $\Lambda_5$ | Integrity/Verification | `channels[k].ipp_executor.integrity` | $\Xi_k$ |
| $\Lambda_6$ | Schema/Template | `channels[k].ipp_object.input.T.schema` | $\Omega_k$ |
| $\Lambda_7$ | Policies/QoS | `channels[k].ipp_executor.policy` (+ internal edge policy) | $\Xi_k$ |
| $\Lambda_8$ | Provenance/Audit | `channels[k].ipp_executor.provenance` (+ internal edge traversal records) | $\Xi_k$ |
| $\Lambda_9$ | Error/Fallback | `channels[k].ipp_executor.error_handling` (+ `internal_timeout`) | $\Xi_k$ |
| $\Lambda_{10}$ | Edge Capability | `channels[k].ipp_executor.edge_capabilities` (external) + `internal_topology.edges` (internal) | $\Xi_k$ — $\tau^*_k$ built in by $\Gamma$ |

### 7.2 Layer Partition Theorem

**Theorem 3 (Layer Partition).** Per channel $k$: $\Lambda = \Lambda_{\Omega,k} \uplus \Lambda_{\Xi,k}$ with $\Lambda_{\Omega,k} = \{\Lambda_1, \Lambda_2, \Lambda_3, \Lambda_4, \Lambda_6\}$ and $\Lambda_{\Xi,k} = \{\Lambda_5, \Lambda_7, \Lambda_8, \Lambda_9, \Lambda_{10}\}$. Internal topology is a declaration in $\mathcal{F}$; its runtime realization ($I^{\text{out}}_k, I^{\text{in}}_k$) belongs to $\Lambda_{\Xi,k}$.

### 7.3 Architectural Principle

> **Declare channels and internal topology; resolve external wiring; construct independently; enforce at the edge with internal routing.** $\mathcal{F}$ declares $n$ independent channels and an optional internal edge topology $\mathcal{E}_{\text{int}}$. $\Gamma$ constructs $2n$ independent runtime peers and wires internal edges into each executor's routing table. External topology is Constructor-resolved per channel; internal topology is Constructor-wired directly from the declaration.

---

## 8. IPP Constructor — Formal Agent Specification

### 8.1 Agent Class Membership

**Definition 9 (Constructor Agent Class).** $\Gamma$ belongs to the agent class $\mathcal{A}$:

$$\mathcal{A} := \{\; a \;|\; a \Vdash \mathcal{F} \times \mathcal{G} \leadsto (\{\, (\Omega_k, \Xi_k[\tau^*_k]) \mid k = 1 \ldots n \,\}, \mathcal{E}_{\text{int}}) \;\}$$

The class $\mathcal{A}$ is deliberately broad, containing $\mathcal{A}_{\text{LLM}}$ (large language models), $\mathcal{A}_{\text{code-gen}}$ (program synthesis systems), $\mathcal{A}_{\text{human}}$ (human operators), and $\mathcal{A}_{\lambda}$ (pure functions — the single-channel backward-compatible case).

### 8.2 Construction Protocol

The seven-step protocol $\mathcal{P}_{\text{construct}}$:

**Steps 1–2 — Construct All Objects.** For each channel $k \in \mathcal{F}.\text{channels}$: parse $\omega_{\text{decl},k}$; instantiate $\Pi_{\text{in},k}, \Pi_{\text{out},k}$; bind $\mathcal{H}_k$ to a handler satisfying $\omega_{\text{decl},k}.\text{process}.\text{description}$; initialize $\sigma_{\Omega,k} \leftarrow \varnothing$; embed $\gamma_{\Omega,k} \leftarrow \text{Ref}(\Gamma)$.

**Steps 3–4 — Configure All Guards.** For each channel $k$: parse $\xi_{\text{decl},k}$; instantiate $\iota_k, \pi_k, \rho_k, \varepsilon_k$.

**Step 5 — Resolve External Topology.** For each channel $k$: $\tau^*_k$ (external components) $= \text{resolve}_k(\mathcal{K}_{\tau,k}, \mathcal{G})$.

**Step 6 — Wire Internal Topology.**
1. Read $\mathcal{E}_{\text{int}}$ from $\mathcal{F}.\text{internal\_topology}$ (empty set if absent);
2. **Validate** that $G_{\text{int}} = (V_{\text{int}}, \mathcal{E}_{\text{int}})$ is a DAG — reject any file containing a structural cycle (Invariant I15);
3. For each internal edge $e = ((c_s, \text{output}), (c_t, \text{input}), \mu, \theta)$:
   - Add $e$ to $I^{\text{out}}_{c_s}$ (outgoing internal edges of the source executor);
   - Add $e$ to $I^{\text{in}}_{c_t}$ (incoming internal edges of the target executor);
   - If $\mu = \text{blocking}$: wire the completion signal path from $\Xi_{c_t}$ back to $\Xi_{c_s}$;
4. Embed $I^{\text{out}}_k, I^{\text{in}}_k$ into each $\Xi_k$'s $\tau^*_k$; embed $\gamma_{\Xi,k}$.

**Step 7 — Return.** $\Gamma$ returns $(\{(\Omega_k, \Xi_k[\tau^*_k])\}_{k=1}^n, \mathcal{E}_{\text{int}})$ and enters the dormant state (Lemma 1).

### 8.3 Recall Semantics

**Definition 16 (Recall Operation).** For channel $k$, entity $E_k \in \{\Omega_k, \Xi_k\}$, with optional new context $\mathcal{G}'_k$:

$$\text{recall}(E_k, \delta'_k, [\mathcal{G}'_k]) := \Gamma(\mathcal{F}[\text{channels}[k] \leftarrow \text{channel}'_k], \mathcal{G}'_k) \quad \text{with atomic swap}$$

For internal topology re-specification:

$$\text{recall\_internal}(\mathcal{E}_{\text{int}}') := \Gamma(\mathcal{F}[\text{internal\_topology} \leftarrow \mathcal{E}_{\text{int}}']) \quad \text{with atomic internal re-wire}$$

```
Per-channel recall:
  Ω_k ──γ_Ω,k──► Γ( F[channels[k] ← channel'_k] ) ──► Ω_k'
  Ξ_k ──γ_Ξ,k──► Γ( K_τ,k × 𝒢'_k ) ──► τ*_k' ──► Ξ_k' (file untouched)

Internal topology re-spec:
  Γ( F[internal_topology ← E_int'] ) ──► new internal wiring into all Ξ_k

Channel addition with internal wiring:
  Γ( F with new channel + updated internal_topology ) ──► (Ω_{n+1}, Ξ_{n+1}) + updated E_int
```

### 8.4 Formal Justification

**Theorem 4 (Insufficiency of Pure Functions).** There exist well-formed IPP Json Files for which no pure function can correctly bind handlers against natural-language `process.description` specifications. An agent $\Gamma \in \mathcal{A}_{\text{LLM}}$ can approximate the solution using learned semantic representations. (Proof: reduction from the halting problem with a natural-language entailment oracle.)

**Theorem 6 (Topology Is Not File-Determinable).** No pure function of $\mathcal{F}$ alone can produce a correct realized external topology, because the wiring depends on which nodes exist in the deployment registry $\mathcal{N} \not\subseteq \mathcal{F}$. External topology is necessarily a constructor-time resolution against the live context. Internal topology, being part of the node's own design, *is* file-determinable and is therefore declared directly.

**Theorem 7 (Resolution Conformance).** $\forall k, \forall \Gamma \in \mathcal{A}, \forall \mathcal{G}: \text{resolve}_k(\mathcal{K}_{\tau,k}, \mathcal{G}) = \tau^*_k \implies \tau^*_k \in \mathcal{T}(\mathcal{K}_{\tau,k})$.

**Theorem 8 (Cross-Channel Non-Interference).** Operations on channel $i$ never block, pause, or invalidate channel $j$. From Theorems 1b, 1c, and Axiom X7. A blocking internal edge suspends only the *source* executor; the target channel and all other channels continue independently.

**Theorem 9 (Internal DAG Property).** $G_{\text{int}} = (V_{\text{int}}, \mathcal{E}_{\text{int}})$ is acyclic. The Constructor rejects any $\mathcal{F}$ whose internal topology contains a cycle at the port level. A structural cycle — where a port reaches itself through internal edges alone, without passing through any handler — is a design error.

---

## 9. Formal Schema — Complete IPP Json File

```json
{
  "$schema": "https://ipp-spec.org/v0.2.8/schema.json",
  "ipp_version": "0.2.8",
  "node_id": "<globally-unique-node-identifier>",
  "channels": [
    {
      "channel_id": "<unique-channel-id>",
      "ipp_object": {
        "input":  { "logical_type": "<type>", "description": "<human-readable>" },
        "process": { "description": "<natural-language transformation description>" },
        "output": { "logical_type": "<type>", "description": "<human-readable>" }
      },
      "ipp_executor": {
        "integrity": {
          "checksum_algorithm": { "type": "string", "enum": ["sha256", "sha512", "blake3"] },
          "signature_required": { "type": "boolean" },
          "verification_endpoint": { "type": ["string", "null"], "format": "uri" },
          "payload_validation_schema": { "type": ["object", "null"] }
        },
        "policy": {
          "max_cost_per_call_usd": { "type": "number", "minimum": 0 },
          "max_latency_ms": { "type": "integer", "minimum": 1 },
          "rate_limit_rps": { "type": "integer", "minimum": 0 },
          "security_clearance": { "type": "string" },
          "retry_policy": {
            "type": "object", "required": ["max_retries", "backoff_strategy"],
            "properties": {
              "max_retries": { "type": "integer", "minimum": 0 },
              "backoff_strategy": { "type": "string", "enum": ["constant", "exponential", "jitter"] }
            }
          }
        },
        "provenance": {
          "audit_level": { "type": "string", "enum": ["none", "summary", "full"] },
          "log_endpoint": { "type": "string", "format": "uri" },
          "chain_of_custody": { "type": "boolean" }
        },
        "error_handling": {
          "fallback_nodes": { "type": "array", "items": { "type": "string" } },
          "circuit_breaker": {
            "type": "object", "required": ["failure_threshold", "recovery_timeout_ms"],
            "properties": {
              "failure_threshold": { "type": "integer", "minimum": 1 },
              "recovery_timeout_ms": { "type": "integer", "minimum": 1 }
            }
          },
          "escalation_policy": {
            "type": "object", "required": ["max_escalation_depth", "escalation_delay_ms"],
            "properties": {
              "max_escalation_depth": { "type": "integer", "minimum": 0 },
              "escalation_delay_ms": { "type": "integer", "minimum": 0 }
            }
          }
        },
        "edge_capabilities": {
          "type": "object",
          "description": "Space of POSSIBLE external edges for this channel. NOT concrete wiring.",
          "required": ["upstream_compatible", "downstream_compatible", "routing_modes", "constraint_envelope"],
          "properties": {
            "upstream_compatible": {
              "type": "array",
              "items": {
                "type": "object",
                "required": ["node_class", "output_logical_type", "edge_count_range", "compatibility"],
                "properties": {
                  "node_class": { "type": "string" },
                  "output_logical_type": { "type": "string" },
                  "edge_count_range": {
                    "type": "object", "required": ["min", "max"],
                    "properties": { "min": { "type": "integer", "minimum": 0 }, "max": { "type": "integer", "minimum": 0 } }
                  },
                  "compatibility": { "type": "string", "enum": ["exact", "convertible", "any"] }
                }
              }
            },
            "downstream_compatible": {
              "type": "array",
              "items": {
                "type": "object",
                "required": ["node_class", "input_logical_type", "edge_count_range", "compatibility"],
                "properties": {
                  "node_class": { "type": "string" },
                  "input_logical_type": { "type": "string" },
                  "edge_count_range": {
                    "type": "object", "required": ["min", "max"],
                    "properties": { "min": { "type": "integer", "minimum": 0 }, "max": { "type": "integer", "minimum": 0 } }
                  },
                  "compatibility": { "type": "string", "enum": ["exact", "convertible", "any"] }
                }
              }
            },
            "routing_modes": { "type": "array", "items": { "type": "string", "enum": ["unicast", "multicast", "broadcast", "anycast", "reduce"] } },
            "constraint_envelope": {
              "type": "object",
              "required": ["max_parallel_edges", "acknowledgment", "backpressure_modes", "resolution_policy"],
              "properties": {
                "max_parallel_edges": { "type": "integer", "minimum": 1 },
                "acknowledgment": { "type": "string", "enum": ["optional", "required", "unsupported"] },
                "backpressure_modes": { "type": "array", "items": { "type": "string", "enum": ["drop", "buffer", "block"] } },
                "resolution_policy": { "type": "string", "enum": ["constructor_resolved", "supervisor_guided", "open"] }
              }
            }
          }
        }
      }
    }
  ],
  "internal_topology": {
    "edges": [
      {
        "from": { "channel_id": "<source-channel>", "port": "output" },
        "to":   { "channel_id": "<target-channel>", "port": "input" },
        "mode": "blocking",
        "timeout_ms": 30000
      }
    ]
  }
}
```

**Where topology lives:**

| Artifact | Location | Nature |
|:---|:---|:---|
| External capability space $\mathcal{K}_{\tau,k}$ | $\mathcal{F}.\text{channels}[k].\text{ipp\_executor}.\text{edge\_capabilities}$ | Static declaration (per channel) |
| Internal topology $\mathcal{E}_{\text{int}}$ | $\mathcal{F}.\text{internal\_topology}$ | Static declaration (node-level) |
| Realized external topology (per channel) | Runtime state of $\Xi_k$ | Dynamic, built by $\Gamma$, never serialized |
| Realized internal routing $I^{\text{out}}_k, I^{\text{in}}_k$ | Runtime state of $\Xi_k$ | Dynamic, built by $\Gamma$, never serialized |
| Resolution events (incl. $\mathcal{G}$ snapshots) | Provenance log of each $\Xi_k$ ($\Lambda_8$) | Every construction and re-wiring is audited |

---

## 10. Design Invariants

The v0.2.8 specification guarantees the following invariants, enforceable by construction:

| # | Invariant | Formal Statement | Enforcement |
|:---|:---|:---|:---|
| **I1** | Separation of Declaration and Enforcement | $\mathcal{F} \cap \mathcal{I} = \varnothing$ | No runtime logic in $\mathcal{F}$; no declarations in $\mathcal{I}$ |
| **I2** | Guardrail Completeness | Per-channel: $\iota_{\text{pre},k} \to \pi_k \to [\Omega_k] \to \iota_{\text{post},k} \to \rho_k \to \tau^*_k$ | Single code path in Executor |
| **I3** | Object-Executor Independence | $\Omega_k \bot \Xi_k$ for each $k$ (Theorem 1a) | Disjoint state spaces; independent lifecycles |
| **I4** | Atomic Hot-Swap | Per-channel atomic swap | Reference-counted replacement |
| **I5** | Recursive Improvability | Per-channel recall with $\text{perf}(E'_k) \geq \text{perf}(E_k)$ | $\gamma_{E,k} \rightsquigarrow \Gamma$ closed-loop cycle |
| **I6** | Audit Completeness | Per-channel hash-chained append-only audit log (Axiom X3, X9) | `audit_verify()` validates chain |
| **I7** | Port Orthogonality | $\Pi_k \cong \Phi_k \times A_k \times T_k$ | Independent factor evolution |
| **I8** | Constructor Independence | $\Gamma \not\subset \mathcal{F}$ | $\Gamma$ replaceable without modifying any $\mathcal{F}$ |
| **I9** | Topology Decoupling | $\nexists \tau_k \subseteq \mathcal{F}$ for any $k$ | Schema forbids concrete external wiring |
| **I10** | Constructor-Specified External Topology | $\tau^*_k = \text{resolve}_k(\mathcal{K}_{\tau,k}, \mathcal{G})$ per channel | Construction Step 5; $\Xi_k$ refuses external writes (X6) |
| **I11** | Topology Mutability Bound | $\tau^*_k$ mutates only through per-channel recall | Recall protocol; every resolution event audited |
| **I12** | Cross-Channel Object Independence | $\forall i \neq j: \Omega_i \bot \Omega_j$ (Theorem 1b) | Disjoint state, handlers, ports, lifecycles |
| **I13** | Cross-Channel Executor Independence | $\forall i \neq j: \Xi_i \bot \Xi_j$ and $\Omega_i \bot \Xi_j$ (Theorem 1c) | Disjoint guardrails, topologies, audit logs |
| **I14** | Cross-Channel Non-Interference | Channel $i$ operations never block, pause, or invalidate channel $j$ (Theorem 8) | Independent construction, execution, recall, destruction |
| **I15** | Internal DAG | $G_{\text{int}} = (V_{\text{int}}, \mathcal{E}_{\text{int}})$ is acyclic (port-level vertices) | Constructor validates at Step 6.2; rejects cyclic files |
| **I16** | Internal Edge Port Correctness | $\forall e \in \mathcal{E}_{\text{int}}: e.\text{from}.\text{port} = \text{output} \land e.\text{to}.\text{port} = \text{input}$ | Schema + Constructor check |
| **I17** | Internal Edge State Isolation | Internal edges carry payloads, not state. $\forall i \neq j$, no state shared through internal edges | Channels remain $\bot$; edges are pure data routing (Theorem 1d) |

**I12 + I13 + I14** deliver the multi-channel property: a single node may carry $n$ heterogeneous information flows, each fully independent and concurrently executable. **I15 + I16 + I17** guarantee that internal topology is well-formed, cycle-free, and does not violate structural independence. Channels remain independently testable, swappable, and improvable even when connected internally.

---

## 11. Summary — The v0.2.8 Formal Model

### 11.1 The Complete System

```
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│                              IPP v0.2.8 — Complete Formal Model                              │
│                                                                                              │
│   F — IPP Json File                               𝒢 — Graph Context (external)               │
│   ┌────────────────────────────────────────┐      registry · candidates · supervisor intent  │
│   │ channels: [channel₁, ..., channelₙ]    │                                                 │
│   │ internal_topology?: { edges: [...] }   │                                                 │
│   └──────────────────┬─────────────────────┘                                                 │
│                      │                                                                       │
│   ┌──────────────────▼─────────────────────┐                                                  │
│   │  Γ — IPP Constructor (Agent)           │◄──────────── 𝒢 (read at resolution)             │
│   │  Steps 1-2: construct Ω_1..Ω_n         │                                                  │
│   │  Steps 3-4: configure Ξ_1..Ξ_n guards  │                                                  │
│   │  Step 5: resolve external τ*_k per ch  │                                                  │
│   │  Step 6: validate DAG, wire E_int      │                                                  │
│   │  Step 7: return ({Ω_k,Ξ_k}, E_int)     │                                                  │
│   └───┬──────────────┬─────────────────────┘                                                  │
│       │              │                                                                        │
│       ▼              ▼                                                                        │
│  ┌──────────────────────────┐    ┌──────────────────────────┐                                │
│  │  Ξ_k  ──►  Ω_k (×n)      │    │  Internal edges wired     │                                │
│  │  · τ*_k (external)       │    │  · I_out_k per executor   │                                │
│  │  · I_out_k, I_in_k       │    │  · I_in_k per executor    │                                │
│  │  · γ_Ξk↝Γ                │    │  · Flow control signals   │                                │
│  └──────────────────────────┘    └──────────────────────────┘                                │
│                                                                                              │
│   All 2n+1 peers pairwise independent (save Ω_k↔Ξ_k cooperation within channel)              │
│   Channels share node_id & Γ only                                                            │
│   Internal edges carry payloads via executor dispatch; no state is shared                    │
│                                                                                              │
│   Re-wiring (external): Ξ_k ──γ_Ξk──► Γ(𝒢'_k) ──► τ*_k' (file untouched)                    │
│   Internal re-spec:      Γ( F[internal_topology ← E_int'] ) ──► atomically re-wire all edges │
│   Channel addition:       Γ( F with new channel ) ──► (Ω_{n+1}, Ξ_{n+1}) + updated E_int     │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 11.2 The Five Core Innovations

1. **Structural Decomposition.** The IPP runtime is factored into three independent entities — $\Gamma$ (Constructor, an autonomous agent), $\Omega$ (Object, the node owning computation), and $\Xi$ (Executor, the edge connector owning guardrails and topology) — where $\Omega \bot \Xi$ and $\Gamma$ is dormant at runtime but recallable by either peer.

2. **Topology Decoupling.** $\mathcal{F}$ declares external edge capability spaces, never concrete wiring. External topology is Constructor-resolved against the live graph context and built into the Executor. The same file, unchanged, yields different correct wirings in different deployments.

3. **Multi-Channel Architecture.** A single IPP Json File declares $n \geq 1$ independent channels, each a complete (object, executor) pair. The Constructor produces $2n$ runtime peers — $n$ objects and $n$ executors — all structurally independent. Channels may carry heterogeneous information types through the same logical node with per-channel handlers, ports, guardrails, topology, and recall.

4. **Internal Edge Topology.** Channels within a node may be directionally connected via declared internal edges with flow control modes (blocking, non_blocking, callback). The internal topology forms a port-level DAG. Internal edges carry payloads without sharing state. This enables complete intra-node processing pipelines to be specified declaratively alongside the channel definitions.

5. **Built-in, Executor-Owned, Recall-Mutable Edges.** All topology — external and internal — is built into the Executor's constructed state, immutable in-band, and mutable only through recall. The graph becomes fluid while files remain stable.

---

## Appendix A: Implementation Checklist

To construct an IPP v0.2.8-compliant system:

### A. IPP Json File
- [ ] Define `$schema`, `ipp_version` ("0.2.8"), `node_id`
- [ ] Declare `channels` array ($n \geq 1$), each with unique `channel_id`
- [ ] Per channel: `ipp_object` (input Port, process description, output Port)
- [ ] Per channel: `ipp_executor` (integrity, policy, provenance, error_handling, edge_capabilities)
- [ ] Ports: implement `core_flow` ($\Lambda_1$–$\Lambda_3$), `accommodation` ($\Lambda_4$, $\Lambda_7$), `template` ($\Lambda_6$)
- [ ] Edge capabilities: declare `upstream_compatible`, `downstream_compatible`, `routing_modes`, `constraint_envelope` — NEVER concrete external wiring
- [ ] Optionally: `internal_topology` with zero or more internal edges

### B. IPP Constructor ($\Gamma$)
- [ ] Implement as an autonomous agent (LLM-based, code-gen, or human)
- [ ] Follow the 7-step construction protocol (§8.2)
- [ ] Step 5: resolve external topology per channel against graph context $\mathcal{G}$
- [ ] Step 6: validate internal topology as a port-level DAG; reject cycles
- [ ] Step 6: wire internal edges into executor routing tables
- [ ] Embed recall references $\gamma_{\Omega,k}$ and $\gamma_{\Xi,k}$ in every peer

### C. IPP Object ($\Omega_k$)
- [ ] Implement input/output Ports per Definition 2
- [ ] Bind handler $\mathcal{H}_k$ satisfying process description
- [ ] Enforce Axioms O1–O5
- [ ] Implement lifecycle FSM (7 states)
- [ ] Channels operate independently; internal edge provenance in $\Lambda_3$

### D. IPP Executor ($\Xi_k$)
- [ ] Implement guardrail envelope: $\iota_{\text{pre},k} \to \pi_k \to [\Omega_k] \to \iota_{\text{post},k} \to \rho_k \to \tau^*_k$
- [ ] Enforce Axioms X1–X9
- [ ] External dispatch via $D^*_k$; internal dispatch via $I^{\text{out}}_k$
- [ ] Flow control enforcement per Axiom X8 (blocking/non_blocking/callback)
- [ ] No bypass path (I2); no in-band topology mutation (X6)
- [ ] Per-channel audit log with internal edge traversal records (X9)

### E. Graph Context & Registry
- [ ] Maintain registry $\mathcal{N}$ of available nodes with per-channel capability spaces
- [ ] Compute candidate edge set $\mathcal{E}_{\text{cand}}$ for external topology
- [ ] Provide supervisor intent $\mathcal{P}_{\text{sup}}$ to the Constructor
- [ ] Internal topology does not require $\mathcal{G}$ — it is declared directly

### F. Verification (All 17 Invariants)
- [ ] I1–I11: Standard invariants (preserved from v0.2.6)
- [ ] I12–I14: Cross-channel independence
- [ ] I15: Internal DAG validated at construction
- [ ] I16: Internal edge port direction enforced
- [ ] I17: Internal edges carry payloads, not state
