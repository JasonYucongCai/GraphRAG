"""
tools.build_cy3 — seed a knowledge graph from the Calabi–Yau threefold research.

Source folder:  assets/20260806 CalabiYau3fold/ResearchReferences/
  • 20260805 Calabi Yau Threefold.ipynb / .html  — the research notes (7 target
    totals h^tot = h11+h21: 17, 28, 29, 66, 80, 81, 92, with verified verdicts)
  • papers/               — 25 PDFs (surveys, classifications, constructions)
  • papers/_extracted/    — pypdf plain-text of 20 papers (encoder source)
  • datasets/             — Kreuzer–Skarke (alltoric/wp4/toric), Davies zoo,
                            TCI Hodge page (30,108 + 2,780 + 10,237 + 210
                            + 30,389 pairs)
  • moment-problem / SDP literature (5 PDFs, background for the Siegel world)

Builds a typed, directed knowledge graph of the CY3 landscape:
  • paper nodes   — every reference (with pdf/txt paths where available)
  • concept nodes — constructions, datasets, mechanisms (KS gap, self-mirror
                    diagonal, toric completeness, Siegel echo, …)
  • total nodes   — the seven target totals with their verified verdicts
  • pair nodes    — the famous Hodge pairs / concrete manifolds
  • typed edges   — papers→concepts, totals→pairs, datasets→concepts, cites

Output (default): database/calabiyau3fold/graph_data/knowledge_graph.json
                  database/calabiyau3fold/graph_data/vectors/index.json
                  database/calabiyau3fold/graph_data/export/  (legacy format)
Every artifact lives inside the project's own graph_data/ folder (see
``database/README.md`` for the canonical layout).

The web control center can serve it with:
    python ui/server.py --graph database/calabiyau3fold/graph_data   # → http://127.0.0.3:8000
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
from pathlib import Path
from typing import Optional

from general_tools.build import export_backward_compatible  # noqa: F401 (re-export)
from general_tools.config import Config
from general_tools.encoder import EncoderLayer
from general_tools.graph import KnowledgeGraph, RELATION_VOCAB

logger = logging.getLogger("general_tools.build_cy3")

# ── Folders ──────────────────────────────────────────────────────────────────
CY3_ROOT = Config.ASSETS_DIR / "20260806 CalabiYau3fold" / "ResearchReferences"
PAPERS_DIR = CY3_ROOT / "papers"
EXTRACTED_DIR = PAPERS_DIR / "_extracted"
DATASETS_DIR = CY3_ROOT / "datasets"
# ALL generated artifacts go to the project's own graph_data/ (canonical layout)
CY3_OUT = Config.project_graph_dir("calabiyau3fold")

# Domain relations not in the base vocab (advisory only — extend for clean logs)
RELATION_VOCAB |= {
    "constructs", "realizes", "introduces", "publishes", "fills",
    "tabulates", "classifies", "documents", "exhibits", "produces",
    "generates", "sources", "underlies", "acts_on", "holds_at",
    "formulates", "constructed_by",
}

# ── Papers (node_id, entryname, arxiv, description, pdf, txt) ────────────────
# txt = None when no extraction exists (scanned/cited-only papers).
PAPERS = [
    # ── the classification core ────────────────────────────────────────────
    ("ks_classification_4d",
     "Complete classification of reflexive polyhedra in four dimensions (Kreuzer & Skarke 2002)",
     "hep-th/0002240",
     "Classification of the 473,800,776 reflexive 4-polytopes → 30,108 Hodge "
     "pairs (h11,h21,chi) of toric CY3 hypersurfaces; every pair mirror-closed.",
     "Kreuzer_Skarke_2000_Complete_classification_4d.pdf", None),
    ("ks_classification_3d",
     "Classification of reflexive polyhedra in three dimensions (Kreuzer & Skarke 1998)",
     "hep-th/9805190",
     "Three-dimensional reflexive polyhedra (K3 background); the base of the "
     "K3-fibration analysis of the 4d classification.",
     "Kreuzer_Skarke_1998_Classification_3d.pdf", None),
    ("ccm_small_hodge",
     "Calabi–Yau Threefolds with Small Hodge Numbers (Candelas–Constantin–Mishra 2018)",
     "arXiv:1602.06303",
     "The 'height' h^tot = h11 + h21; tip of the Hodge plot (h^tot ≤ 24); "
     "Table 1: the height-17 rows (1,16), (4,13), (15,2).",
     "Candelas_Constantin_Mishra_2018_Small_Hodge_Numbers.pdf",
     "Candelas_Constantin_Mishra_2018_Small_Hodge_Numbers.txt"),
    ("candelas_davies",
     "New Calabi–Yau Manifolds with Small Hodge Numbers (Candelas–Davies 2010)",
     "arXiv:0809.4681",
     "Source of the total-17 pairs (1,16) and (4,13): Z3-quotients of the "
     "tri-cubic and of CICYs. Scanned (image-only) PDF — not text-extractable.",
     "Candelas_2008_New_CY_Small_Hodge_Numbers.pdf", None),
    ("davies_zoo",
     "The Expanding Zoo of Calabi–Yau Threefolds (Davies 2011)",
     "arXiv:1103.3156",
     "The 'zoo': 30,389 Hodge pairs known by 2011 with per-pair references; "
     "281 non-toric pairs; small-Hodge-number discussion.",
     "Davies_2011_Expanding_Zoo_CY3.pdf", "Davies_2011_Expanding_Zoo_CY3.txt"),
    ("batyrev_kreuzer_conifold",
     "Constructing new Calabi–Yau 3-folds and their mirrors via conifold transitions "
     "(Batyrev–Kreuzer 2010)",
     "arXiv:0802.3376",
     "Conifold transitions from toric constructions: fills the KS gap with "
     "(2,26), (3,25), (1,28), (1,65), (1,79), …",
     "Batyrev_Kreuzer_2008_Conifold_Transitions.pdf", None),
    ("green_hubsch_lutken",
     "All Hodge Numbers of All Complete Intersection Calabi–Yau Manifolds "
     "(Green–Hübsch–Lütken 1989)",
     "CQG 6 (1989) 105",
     "The CICY classification: 7,890 Hodge pairs of complete intersections in "
     "products of projective spaces; includes the four-quadrics [2 2 2 2]⊂P7 = (1,65).",
     None, None),
    ("kreuzer_riegler_sahakyan",
     "Toric complete intersections and weighted projective space "
     "(Kreuzer–Riegler–Sahakyan 2003)",
     "arXiv:math/0103214",
     "The TCI construction ('Kreuzer:2007' in Davies' refs) — the tool that "
     "reaches into the toric gap: 12 of the 17 pairs at total 28.",
     None, None),
    ("freitag_salvati_siegel",
     "On Siegel threefolds with a projective Calabi–Yau model "
     "(Freitag–Salvati Manni 2011)",
     "arXiv:1103.2040",
     "The Siegel world: rigid CY3 quotients with Euler numbers 2,4,6,…,140 — "
     "including chi = 28, 80, 92 (h11 = 14, 40, 46) and the total-17 pair (15,2) = X̂/Z3².",
     "Freitag_SalvatiManni_2011_Siegel_threefolds_CY_model.pdf",
     "Freitag_SalvatiManni_2011_Siegel_threefolds_CY_model.txt"),
    ("cynk_freitag_salvati",
     "The geometry and arithmetic of a Calabi–Yau Siegel threefold "
     "(Cynk–Freitag–Salvati Manni 2011)",
     "arXiv:1004.2997",
     "Geometry and arithmetic of the Siegel modular threefold underlying the "
     "rigid CY3 story.",
     "Cynk_Freitag_SalvatiManni_Siegel_CY3.pdf",
     "Cynk_Freitag_SalvatiManni_Siegel_CY3.txt"),
    ("he_jejjala_pontiggia",
     "Patterns in Calabi–Yau Distributions (He–Jejjala–Pontiggia 2016)",
     "arXiv:1512.01579",
     "The Planckian (blackbody) law of the total h11+h21 with the 22-shift; "
     "r-curves; Fig. 4a tabulates r = 28, 29, Fig. 4b highlights r = 42, 54, 66.",
     "Patterns in Calabi–Yau Distributions 1512.01579v3.pdf",
     "Patterns in Calabi-Yau Distributions 1512.01579v3.txt"),
    ("braun_24cell",
     "The 24-Cell and Calabi–Yau Threefolds with Hodge Numbers (1,1) (Braun 2012)",
     "arXiv:1102.4880",
     "The (1,1) floor of the landscape: free quotients of the 24-cell manifold "
     "X20,20 — extends the self-mirror diagonal below the toric start.",
     None, None),
    ("cgl_cicy_quotients",
     "Hodge Numbers for All CICY Quotients (Constantin–Gray–Lukas 2017)",
     "arXiv:1607.01830",
     "Quotient tables: (4,13) multiply realized as Z3-quotients of CICYs with "
     "(6,33), (8,35), …",
     "Constantin_Gray_Lukas_2016_CICY_Quotients.pdf",
     "Constantin_Gray_Lukas_2016_CICY_Quotients.txt"),
    ("klemm_topological_strings",
     "Topological string amplitudes, complete intersection Calabi–Yau spaces and "
     "threshold corrections (Klemm–Kreuzer–Riegler–Scheidegger 2005)",
     "arXiv:hep-th/0410018",
     "Topological strings on CICYs; the (1,79)/(2,78) region at total 80.",
     "Klemm_2004_CICY_Topological_Strings.pdf", None),
    ("ccs_k3_fibrations",
     "An Abundance of K3 Fibrations from Polyhedra with Interchangeable Parts "
     "(Candelas–Constantin–Skarke 2013)",
     "arXiv:1207.4792",
     "The Hodge plot with axes chi and height y = h11+h21; half-mirror symmetry; "
     "webs of elliptic-K3 fibrations.",
     "Candelas_Constantin_Skarke_2012_K3_Fibrations.pdf",
     "Candelas_Constantin_Skarke_2012_K3_Fibrations.txt"),
    ("constantin_thesis",
     "Heterotic String Models on Smooth Calabi–Yau Threefolds (Constantin 2018, thesis)",
     "arXiv:1808.09993",
     "Fractal structure of the Hodge plot; additivity of Hodge numbers under "
     "mixing tops/bottoms; topmost self-mirror (251,251); extremal (11,491).",
     "Constantin_2018_Heterotic_Models_CY3.pdf",
     "Constantin_2018_Heterotic_Models_CY3.txt"),
    ("hosono_takagi",
     "Determinantal quintics and mirror symmetry of Reye congruences "
     "(Hosono–Takagi 2013)",
     "arXiv:1208.1813",
     "The (52,2) family — the rare h21=2 species outside the Siegel world.",
     None, None),
    ("mnq_codim4",
     "Constructions and deformations of Calabi–Yau 3-folds in codimension 4 "
     "(Moshin–Nazir–Qureshi 2024)",
     "arXiv:2312.17341",
     "New realizations in codimension 4 — including (3,62) (already known in "
     "Davies 2011; new realization, not a new pair).",
     "Moshin_Nazir_Qureshi_2023_CY_codim4.pdf", "Moshin_Nazir_Qureshi_2023_CY_codim4.txt"),
    ("macfadden_bound",
     "Further Bounding the Kreuzer–Skarke Landscape (MacFadden–Orevkov–Stepniczka 2026)",
     "arXiv:2602.16909",
     "Bounds the number of diffeomorphism classes of toric CY3s by 10^296 — "
     "the multiplicity question is genuinely huge.",
     "Further Bounding the Kreuzer-Skarke Landscape 2602.16909v2.pdf", None),
    ("leontaris_shukla",
     "Towards Systematics of Calabi–Yau Landscape for String Cosmology "
     "(Leontaris–Shukla 2026)",
     "arXiv:2604.28189",
     "Newest landscape review: the two main datasets — CICYs (7,890 pairs) and "
     "toric hypersurfaces (30,108 pairs).",
     "Leontaris_Shukla_2026_Systematics_CY_Landscape.pdf",
     "Leontaris_Shukla_2026_Systematics_CY_Landscape.txt"),
    # ── 2024–2026 ML / triangulation studies (no new Hodge pairs) ─────────
    ("macfadden_dna",
     "The DNA of Calabi–Yau Hypersurfaces (MacFadden–Schachner–Sheridan 2024)",
     "arXiv:2405.08871",
     "Triangulation statistics of the 473M polytopes at fixed h11 = 86, 128; "
     "no new Hodge pairs.",
     "MacFadden_etal_2024_DNA_CY_Hypersurfaces.pdf", "MacFadden_etal_2024_DNA_CY_Hypersurfaces.txt"),
    ("macfadden_vex",
     "Calabi–Yau Threefolds from Vex Triangulations (MacFadden–Sheridan 2025)",
     "arXiv:2512.14817",
     "Vex triangulations of reflexive polytopes; diffeomorphism-level statistics; "
     "no new Hodge pairs.",
     "MacFadden_Sheridan_2025_Vex_Triangulations.pdf", "MacFadden_Sheridan_2025_Vex_Triangulations.txt"),
    ("macfadden_gnn",
     "Sampling Triangulations and CYs with Autoregressive GNNs (MacFadden 2026)",
     "arXiv:2605.27770",
     "Autoregressive GNN sampling over triangulations; no new Hodge pairs.",
     "MacFadden_2026_Sampling_CY_GNNs.pdf", "MacFadden_2026_Sampling_CY_GNNs.txt"),
    ("yip_transforming",
     "Transforming Calabi–Yau Constructions (Yip et al. 2025)",
     "arXiv:2507.03732",
     "Transformer-generated triangulations; no new Hodge pairs.",
     "Yip_etal_2025_Transforming_CY_Constructions.pdf", "Yip_etal_2025_Transforming_CY_Constructions.txt"),
    ("berglund_genetic",
     "New Calabi–Yau Manifolds from Genetic Algorithms (Berglund–He–Heyes–… 2023)",
     "arXiv:2306.06159",
     "Genetic algorithms over reflexive polytopes → new CY four-folds (not "
     "threefolds); no new CY3 Hodge pairs.",
     "Berglund_etal_2023_New_CY_Genetic_Algorithms.pdf",
     "Berglund_etal_2023_New_CY_Genetic_Algorithms.txt"),
    ("cynk_double_octic",
     "Classification of double octic CY3s (Cynk–Kocel-Cynk)",
     "arXiv:2602.19413 / 1612.04364",
     "Double octic double covers of P3: 455 arrangement types; pairs with "
     "h21 ≤ 1; no new pairs at our totals.",
     None, None),
    ("group_invariant_ml",
     "Group-invariant machine learning on the Kreuzer–Skarke dataset (2024)",
     "Phys. Lett. B (2024)",
     "Group-equivariant ML statistics over the KS dataset.",
     "Group-invariant machine learning on the Kreuzer-Skarke dataset "
     "1-s2.0-S0370269324005549-main.pdf",
     "Group-invariant machine learning on the Kreuzer-Skarke dataset "
     "1-s2.0-S0370269324005549-main.txt"),
    ("searching_k3_fibrations",
     "Searching for K3 Fibrations (Kreuzer–Skarke 1996)",
     "arXiv:hep-th/9610154",
     "The 184,026 IP weight systems → 10,237 Hodge pairs (toric.spec): the "
     "K3-fibered toric CY3s.",
     "Searching for K3 Fibrations 9610154v1.pdf", "Searching for K3 Fibrations 9610154v1.txt"),
    ("ks_axiverse",
     "The Kreuzer–Skarke Axiverse (Goodsell–Ringwald 2018)",
     "arXiv:1808.01282",
     "Axion physics over the KS landscape (30,108 pairs, mirror-closed).",
     "The Kreuzer-Skarke Axiverse 1808.01282v1.pdf", "The Kreuzer-Skarke Axiverse 1808.01282v1.txt"),
    ("he_landscape",
     "The Calabi–Yau Landscape: from Geometry, to Physics, to Machine-Learning "
     "(He 2018)",
     "arXiv:1812.02893",
     "Standard landscape review (with Bao–He–Hirst–… arXiv:2001.01212).",
     "He_2018_CY_Landscape_review.pdf", "He_2018_CY_Landscape_review.txt"),
    # ── one-parameter / hypergeometric world ──────────────────────────────
    ("almkvist_hypergeometric",
     "Tables of Calabi–Yau equations (Almkvist–van Enckevort–van Straten–Zudilin 2005)",
     "arXiv:math/0507430",
     "The 14 hypergeometric one-parameter spectra; the quintic mirror (1,101) "
     "and octic double solid (1,149) live here.",
     "Almkvist_etal_2005_Tables_CY_equations.pdf", "Almkvist_etal_2005_Tables_CY_equations.txt"),
    ("doran_morgan",
     "Mirror symmetry and integral variations of Hodge structure (Doran–Morgan)",
     "arXiv:math/0505272",
     "Classifies one-parameter mirror models (Doran–Morgan list).",
     None, None),
    ("hua_quotients",
     "Free quotients of Calabi–Yau complete intersections (Hua 2007)",
     "arXiv:0707.4339",
     "Free group actions on the four-quadrics (1,65): orders 2, 4, 8, 16, 32 — "
     "the quotient tower (1,33), (1,17), (1,9), (1,5), (1,3).",
     None, None),
    ("bini_favale",
     "Groups acting freely on Calabi–Yau threefolds embedded in a product of "
     "del Pezzo surfaces (Bini–Favale 2012)",
     "arXiv:1104.0247",
     "Free quotients realizing (4,13), (6,22), …",
     None, None),
    ("kapustka",
     "Primitive contractions of Calabi–Yau threefolds II (Kapustka 2009)",
     "arXiv:0707.2488",
     "Contractions realizing non-toric pairs at totals 66/80.",
     None, None),
    # ── moment problem / SDP background (Siegel & positivity world) ───────
    ("laurent_sos",
     "Sums of squares, moment matrices and optimization over polynomials "
     "(Laurent 2009)",
     "Emerging Applications of Algebraic Geometry (2009)",
     "SOS/moment-matrix theory for polynomial optimization.",
     "Laurent_2009_SOS_Moment_Matrices_Optimization.pdf", None),
    ("schmudgen_moment",
     "Ten Lectures on the Moment Problem (Schmüdgen 2017)",
     "arXiv:2008.12698",
     "The classical moment problem — background for the Siegel/moment world.",
     "Schmudgen_2008.12698v1_Ten_Lectures_on_the_Moment_Problem.pdf", None),
    ("josz_henrion",
     "Strong duality in Lasserre's hierarchy for polynomial optimization "
     "(Josz–Henrion 2016)",
     "Optim. Lett. (2016)",
     "Strong duality of the Lasserre SDP hierarchy.",
     "Josz_Henrion_2014_Lasserre_Strong_Duality.pdf", None),
    ("deklerk_laurent",
     "A survey on semidefinite programming and its applications to polynomial "
     "optimization (de Klerk–Laurent 2018)",
     "arXiv:1808.03457",
     "SDP survey covering the moment/Positivstellensatz toolbox.",
     "deKlerk_Laurent_2018_Survey_Moment_SDP.pdf", None),
    ("moment_problem_book",
     "The Moment Problem (book)",
     "GTM 277 (2017)",
     "Monograph on moment problems and orthogonal polynomials.",
     "The-Moment-Problem.pdf", None),
]

# ── Concepts (node_id, entryname, description) ───────────────────────────────
CONCEPTS = [
    ("total_hodge_number", "Total Hodge Number h^tot = h11 + h21",
     "The 'height' of the Hodge plot (Candelas–Constantin–Skarke); the "
     "dimension of the moduli space. Mirror invariant. Odd values 17/29/81 "
     "are only possible for this definition, not the full Hodge sum."),
    ("hodge_diamond", "Hodge Diamond & Euler Characteristic",
     "h^00=h^33=h^30=h^03=1, h^10=h^20=0, h^22=h^11, h^31=h^21; "
     "chi = 2(h11 − h21); chi ≡ 0 (mod 4) for even totals, ≡ 2 (mod 4) for odd."),
    ("mirror_symmetry", "Mirror Symmetry",
     "Mirror swaps (h11,h21) ↔ (h21,h11); the total is mirror invariant; "
     "self-mirror pairs have chi = 0; every toric pair is mirror-closed."),
    ("self_mirror_diagonal", "Self-Mirror Diagonal (h11 = h21)",
     "136 toric pairs with chi=0, contiguous h = 14…99 below 100 (first gap at "
     "h=118); first pair (14,14) at total 28; every even total 28–198 carries "
     "one; the true known diagonal starts at (1,1) (Braun's 24-cell)."),
    ("ks_gap", "The Kreuzer–Skarke Gap",
     "No toric CY3 has total below 22: totals 2–21, 23, 24, 27 are empty in "
     "alltoric.spec; (1,21)/(21,1) are the minimal toric pairs."),
    ("rigid_cy3", "Rigid CY3s (h21 = 0)",
     "No toric CY3 is rigid (KS h21 ≥ 1); every known rigid CY3 is non-toric — "
     "almost all from the Siegel world: (14,0), (28,0), (40,0), (46,0), …"),
    ("one_parameter_world", "One-Parameter World (h11 = 1)",
     "51 known h11=1 pairs; only 5 toric: (1,21), (1,101), (1,103), (1,145), "
     "(1,149); the quintic mirror (1,101) and octic double solid (1,149); "
     "the 14 hypergeometric spectra (Almkvist et al.)."),
    ("cicy", "Complete Intersection CYs (CICY)",
     "7,890 CICY Hodge pairs (Green–Hübsch–Lütken); includes the four-quadrics "
     "[2 2 2 2] ⊂ P7 = (1,65); Klemm et al. topological strings; Kapustka "
     "contractions; Hosono–Takagi determinantal quintics (52,2)."),
    ("tci_construction", "Toric Complete Intersections (TCI)",
     "Kreuzer–Riegler–Sahakyan construction (210 pairs, unpublished data): the "
     "gap-filler — 12 of 17 pairs at total 28 are TCIs."),
    ("conifold_transition", "Conifold Transitions",
     "Batyrev–Kreuzer construction: (2,26), (3,25), (1,28) at the tip; the "
     "extremal points (1,65), (2,64) at 66 and (1,79), (2,78) at 80."),
    ("free_quotient", "Free Quotients",
     "Group actions with nontrivial pi_1: the tip pairs (1,16), (4,13), (15,2); "
     "Hua's tower; Bini–Favale; Constantin–Gray–Lukas CICY quotient tables."),
    ("siegel_threefold", "Siegel Modular Threefolds",
     "Freitag–Salvati Manni quotients: (15,2) at total 17; rigid quotients with "
     "chi = 28, 80, 92 (h11 = 14, 40, 46); the projective-CY Siegel story "
     "(Cynk–Freitag–Salvati Manni)."),
    ("double_octic", "Double Octic CY3s",
     "Double covers of P3 branched over 8 planes: 455 arrangement types "
     "(Cynk–Kocel-Cynk); pairs with h21 ≤ 1."),
    ("codim4_construction", "Codimension-4 Constructions",
     "Moshin–Nazir–Qureshi: smooth CY3 in codimension 4; (3,62) — a new "
     "realization of a known pair (already in Davies 2011)."),
    ("weighted_p4", "Weighted-P4 Hypersurfaces",
     "7,555 hypersurfaces → 2,780 pairs (wp4.spec); the self-mirror (33,33) "
     "is one; 50 of the 86 diagonal pairs below 100."),
    ("k3_fibration", "K3-Fibered Toric CY3s",
     "184,026 IP weight systems → 10,237 pairs (toric.spec); true K3-fibered "
     "flag = reflexive projection P ≥ 1 in Hodge.K3.gz; zero K3-fibered models "
     "at total 28; odd totals ~26–29% vs even ~67–70%."),
    ("hua_tower", "Hua's Free-Quotient Tower",
     "Free Z2/Z4/… actions on the four-quadrics (1,65): (1,65) → (1,33) → "
     "(1,17) → (1,9) → (1,5) → (1,3); totals 66 → 34 → 18 → 10 → 6 → 4; "
     "total 66 is the root."),
    ("non_toric_ladders", "The Non-Toric Ladders (h11 = 1…5)",
     "The hand-built toolbox runs on five ladders that die out: last hits "
     "(1,129)@130, (2,112)@114, (3,113)@116, (4,95)@99, (5,102)@107; a total is "
     "100% toric iff missed by all five simultaneously."),
    ("toric_completeness", "100% Toric Totals & the 85 Transition",
     "Below 85 only 25, 75, 76, 81 are 100% toric (81 is the largest); 85–130: "
     "78%; 131–280: 150 consecutive; 81 is 100% because of a double gap in the "
     "non-toric ladder (h11=1 skips 80, h11=2 skips 79)."),
    ("self_eigen_presentation", "Self-Eigen Presentations (degree = total)",
     "Hypersurface degree equals the total and the pair is self-mirror: "
     "(33,33) = P(3,12,14,15,22)[66], (46,46) = P(2,12,18,23,37)[92]; absent at "
     "80; recurs at ~25 even totals in the landscape (not unique)."),
    ("siegel_echo", "The Siegel Echo (chi = total)",
     "chi(14,0) = 28, chi(40,0) = 80, chi(46,0) = 92: rigid Siegel quotients "
     "whose Euler number equals the target total, with h11 = total/2."),
    ("plankian_law", "Planckian Distribution of the Total",
     "He–Jejjala–Pontiggia: pair frequencies per total follow the blackbody "
     "law f(x) = A / (x^n (e^{b/(x−22)} − 1)) — the 22-shift encodes the KS "
     "gap; r-curves decompose into residue classes mod 6."),
    ("moment_problem", "Moment Problem / SDP Toolbox",
     "Laurent, Schmüdgen, Josz–Henrion, de Klerk–Laurent: SOS/moment theory "
     "background — the positivity world behind the Siegel/moment analysis."),
    ("ml_landscape", "Machine Learning on the CY Landscape",
     "Group-invariant ML, GNN sampling (MacFadden), DNA of hypersurfaces, "
     "genetic algorithms (Berglund), transformers (Yip): all triangulation-"
     "level statistics — no new Hodge pairs."),
]

# ── Datasets (node_id, entryname, description, files) ────────────────────────
DATASETS = [
    ("ks_dataset", "Kreuzer–Skarke Dataset (alltoric.spec)",
     "All 473,800,776 reflexive 4-polytopes → 30,108 distinct Hodge pairs "
     "(h11,h21,chi); h11,h21 ∈ [1,491]; mirror-closed; min total 22.",
     ["alltoric.spec", "alltoric.spec.gz"]),
    ("wp4_dataset", "Weighted-P4 Dataset (wp4.spec)",
     "7,555 hypersurfaces in weighted P4 → 2,780 pairs.",
     ["wp4.spec", "wp4.spec.gz"]),
    ("ipws_dataset", "IP Weight Systems Dataset (toric.spec + Hodge.K3.gz)",
     "184,026 IP weight systems → 10,237 pairs; per-model file Hodge.K3.gz "
     "with M/N point counts and reflexive-projection flags P ≥ 1 (true "
     "K3-fibered); 38% of toric.spec pairs are mirror-swapped vs Hodge.K3.",
     ["toric.spec", "toric.spec.gz", "Hodge.K3", "Hodge.K3.gz"]),
    ("tci_dataset", "TCI Hodge Data (Kreuzer 0103214.html)",
     "Unpublished Kreuzer–Riegler–Sahakyan Hodge data: 210 toric complete "
     "intersection pairs parsed from the HTML page.",
     ["Kreuzer_TCI_hodge_data_0103214.html"]),
    ("davies_zoo_dataset", "Davies Zoo (hodge_list_davies_*.txt)",
     "30,389 pairs known by 2011 with per-pair reference tags; 281 non-toric "
     "(quotients, conifold/hyperconifold, Pfaffian, gCICY, Siegel, …).",
     ["hodge_list_davies_sorted_h.txt", "hodge_list_davies_sorted_total.txt",
      "hodge_refs_davies.txt"]),
]

# ── The seven target totals (node_id, entryname, verdict) ────────────────────
TOTALS = [
    ("total_17", "Total Hodge Number 17",
     "UNIQUE — below the KS gap (22); 3 known pairs, 0 toric; all three are "
     "free quotients (pi_1 ≠ 1): (1,16) tri-cubic/Z3, (4,13) CICY-quotients, "
     "(15,2) Siegel X̂/Z3²; no new pair since 2011."),
    ("total_28", "Total Hodge Number 28",
     "UNIQUE — first self-mirror total (14,14) (toric diagonal starts at 14); "
     "contains the rigid (28,0) (Siegel); zero K3-fibered models; most "
     "non-toric total ≥ 22 (10 of 17 pairs; TCI fills the gap); statistically "
     "anomalous (−50% vs local expectation)."),
    ("total_29", "Total Hodge Number 29",
     "MILD — neighbour of 28; 8 pairs, 6 toric; extreme point (1,28) with "
     "chi = −54; statistically anomalous (−47%)."),
    ("total_66", "Total Hodge Number 66",
     "SPECIAL — self-mirror (33,33) is generic, but total 66 contains the "
     "four-quadrics CICY (1,65): the root of Hua's free-quotient tower and of "
     "the Siegel story; the only plain-CICY one-parameter pair at our totals; "
     "self-eigen presentation P(3,12,14,15,22)[66]."),
    ("total_80", "Total Hodge Number 80",
     "GENERIC — self-mirror (40,40) is generic (every even total 28–198 has "
     "one); only the Siegel chi=80 echo is a curiosity; non-toric (1,79),(2,78)."),
    ("total_81", "Total Hodge Number 81",
     "NOTABLE — 100% toric (76/76) — the largest 100%-toric total below 85 "
     "(set is {25, 75, 76, 81}); 100% because of a double gap in the non-toric "
     "ladder (h11=1 skips 80, h11=2 skips 79); lowest wps fraction (3.9%)."),
    ("total_92", "Total Hodge Number 92",
     "NOTABLE-BUT-GENERAL — 100% toric (89/89) is the norm by r=92; closed by "
     "the toric (2,90) (lattice luck); Siegel chi=92 echo (46,0); self-eigen "
     "P(2,12,18,23,37)[92]; most populated of the seven."),
]

# ── Famous Hodge pairs / concrete manifolds ──────────────────────────────────
PAIRS = [
    ("pair_1_16", "(1,16) — tri-cubic quotient",
     "X = (3,3,3) ⊂ P2×P2×P2, X/Z3; chi = −30; total 17. CCM Table 1, "
     "Candelas–Davies 0809.4681."),
    ("pair_4_13", "(4,13) — Z3-quotients of CICYs",
     "chi = −18; total 17; multiply realized as CICY quotients "
     "(Constantin–Gray–Lukas 1607.01830; Bini–Favale)."),
    ("pair_15_2", "(15,2) — Siegel modular threefold quotient",
     "X̂/Z3²; chi = +26; total 17. Freitag–Salvati Manni 1103.2040."),
    ("pair_14_14", "(14,14) — first self-mirror toric pair",
     "chi = 0; total 28; the smallest pair with h11 = h21 in the KS dataset; "
     "also a TCI."),
    ("pair_28_0", "(28,0) — rigid Siegel quotient",
     "chi = 56; total 28; NOT in Davies' list (paper-only example); rigid CY3s "
     "are never toric."),
    ("pair_1_28", "(1,28) — conifold transition",
     "chi = −54; total 29; the extreme point of its anti-diagonal. "
     "Batyrev–Kreuzer 0802.3376."),
    ("pair_1_65", "(1,65) — the four-quadrics CICY",
     "The complete intersection [2 2 2 2] ⊂ P7; chi = −128; total 66; root of "
     "Hua's free-quotient tower (1,33),(1,17),(1,9),(1,5),(1,3) and the "
     "variety behind the Siegel modular story."),
    ("pair_33_33", "(33,33) — self-mirror weighted-P4 hypersurface",
     "chi = 0; total 66; 29 IPWS realizations incl. P(3,12,14,15,22)[66] "
     "(self-eigen) and a P:3 model (three K3 fibrations); mid-range "
     "multiplicity (max (95,95) = 95)."),
    ("pair_40_40", "(40,40) — self-mirror K3-fibered pair",
     "chi = 0; total 80; 8 IPWS realizations; NO degree-80 (self-eigen) "
     "realization; Siegel echo chi(40,0) = 80."),
    ("pair_46_46", "(46,46) — self-mirror pair",
     "chi = 0; total 92; 13 IPWS realizations incl. P(2,12,18,23,37)[92] "
     "(self-eigen); Siegel echo chi(46,0) = 92."),
    ("pair_2_90", "(2,90) — the toric lattice-luck point",
     "chi = −176; total 92; the only target total where the (2,h21) point is "
     "toric — closes the anti-diagonal (at 28/66/80 the (2,·) point is "
     "non-toric, which is why those totals are not 100%)."),
    ("pair_1_101", "(1,101) — the quintic mirror",
     "chi = −200; the famous one-parameter mirror model (Doran–Morgan; "
     "Almkvist et al. hypergeometric spectra)."),
    ("pair_1_149", "(1,149) — the octic double solid",
     "chi = −296; the largest-h21 one-parameter toric pair."),
    ("pair_1_1", "(1,1) — Braun's 24-cell manifold",
     "chi = 0; free quotients of X20,20 (the 24-cell); the floor of the known "
     "self-mirror diagonal (below the toric start at 14)."),
    ("pair_251_251", "(251,251) — topmost self-mirror",
     "chi = 0; the self-dual polytope ⟨min|max⟩; top of the toric diagonal."),
    ("pair_3_62", "(3,62) — codimension-4 family",
     "chi = −118; total 65; MNQ 2312.17341 provide a NEW realization of a pair "
     "already in Davies 2011 (Batyrev–Kreuzer, Klemm et al.)."),
]

# ── Edges: (source, target, relation) ────────────────────────────────────────
SEED_EDGES = [
    # papers → datasets
    ("ks_classification_4d", "ks_dataset", "defines"),
    ("davies_zoo", "davies_zoo_dataset", "publishes"),
    ("kreuzer_riegler_sahakyan", "tci_dataset", "publishes"),
    ("searching_k3_fibrations", "ipws_dataset", "sources"),
    # papers → concepts
    ("ks_classification_4d", "mirror_symmetry", "enables"),
    ("ks_classification_3d", "k3_fibration", "related_to"),
    ("ccm_small_hodge", "total_hodge_number", "defines"),
    ("ccm_small_hodge", "total_17", "documents"),
    ("candelas_davies", "pair_1_16", "constructs"),
    ("candelas_davies", "pair_4_13", "constructs"),
    ("davies_zoo", "non_toric_ladders", "documents"),
    ("batyrev_kreuzer_conifold", "conifold_transition", "introduces"),
    ("batyrev_kreuzer_conifold", "pair_1_28", "constructs"),
    ("green_hubsch_lutken", "cicy", "defines"),
    ("green_hubsch_lutken", "pair_1_65", "realizes"),
    ("kreuzer_riegler_sahakyan", "tci_construction", "introduces"),
    ("kreuzer_riegler_sahakyan", "total_28", "fills"),
    ("freitag_salvati_siegel", "siegel_threefold", "constructs"),
    ("freitag_salvati_siegel", "pair_15_2", "constructs"),
    ("freitag_salvati_siegel", "pair_28_0", "constructs"),
    ("freitag_salvati_siegel", "siegel_echo", "produces"),
    ("cynk_freitag_salvati", "siegel_threefold", "describes"),
    ("he_jejjala_pontiggia", "plankian_law", "formulates"),
    ("he_jejjala_pontiggia", "total_28", "tabulates"),
    ("he_jejjala_pontiggia", "total_29", "tabulates"),
    ("he_jejjala_pontiggia", "total_66", "tabulates"),
    ("braun_24cell", "pair_1_1", "constructs"),
    ("cgl_cicy_quotients", "free_quotient", "uses"),
    ("cgl_cicy_quotients", "pair_4_13", "realizes"),
    ("klemm_topological_strings", "cicy", "uses"),
    ("ccs_k3_fibrations", "k3_fibration", "classifies"),
    ("ccs_k3_fibrations", "total_hodge_number", "uses"),
    ("constantin_thesis", "mirror_symmetry", "describes"),
    ("hosono_takagi", "cicy", "related_to"),
    ("mnq_codim4", "codim4_construction", "introduces"),
    ("mnq_codim4", "pair_3_62", "constructs"),
    ("macfadden_bound", "ks_dataset", "evaluates"),
    ("leontaris_shukla", "ks_dataset", "reviews"),
    ("leontaris_shukla", "cicy", "reviews"),
    ("macfadden_dna", "ml_landscape", "applied_in"),
    ("macfadden_vex", "ml_landscape", "applied_in"),
    ("macfadden_gnn", "ml_landscape", "applied_in"),
    ("yip_transforming", "ml_landscape", "applied_in"),
    ("berglund_genetic", "ml_landscape", "applied_in"),
    ("group_invariant_ml", "ml_landscape", "applied_in"),
    ("searching_k3_fibrations", "k3_fibration", "classifies"),
    ("ks_axiverse", "ks_dataset", "evaluates"),
    ("he_landscape", "mirror_symmetry", "reviews"),
    ("he_landscape", "total_hodge_number", "reviews"),
    ("almkvist_hypergeometric", "one_parameter_world", "tabulates"),
    ("doran_morgan", "one_parameter_world", "classifies"),
    ("hua_quotients", "hua_tower", "constructs"),
    ("hua_quotients", "pair_1_65", "acts_on"),
    ("bini_favale", "free_quotient", "uses"),
    ("bini_favale", "pair_4_13", "realizes"),
    ("kapustka", "cicy", "related_to"),
    ("cynk_double_octic", "double_octic", "classifies"),
    ("double_octic", "non_toric_ladders", "part_of"),
    ("laurent_sos", "moment_problem", "describes"),
    ("schmudgen_moment", "moment_problem", "describes"),
    ("josz_henrion", "moment_problem", "describes"),
    ("deklerk_laurent", "moment_problem", "describes"),
    ("moment_problem_book", "moment_problem", "describes"),
    # datasets → concepts
    ("ks_dataset", "mirror_symmetry", "realizes"),
    ("ks_dataset", "ks_gap", "exhibits"),
    ("ks_dataset", "self_mirror_diagonal", "contains"),
    ("ks_dataset", "rigid_cy3", "evidence_for"),
    ("wp4_dataset", "weighted_p4", "realizes"),
    ("wp4_dataset", "self_mirror_diagonal", "contains"),
    ("ipws_dataset", "k3_fibration", "realizes"),
    ("ipws_dataset", "self_eigen_presentation", "contains"),
    ("tci_dataset", "tci_construction", "realizes"),
    ("davies_zoo_dataset", "total_hodge_number", "documents"),
    ("davies_zoo_dataset", "non_toric_ladders", "documents"),
    ("davies_zoo_dataset", "one_parameter_world", "documents"),
    ("davies_zoo_dataset", "pair_3_62", "documents"),
    # concepts → concepts
    ("hodge_diamond", "total_hodge_number", "defines"),
    ("mirror_symmetry", "self_mirror_diagonal", "contains"),
    ("siegel_threefold", "rigid_cy3", "constructs"),
    ("siegel_threefold", "pair_28_0", "constructs"),
    ("siegel_threefold", "pair_15_2", "constructs"),
    ("siegel_threefold", "siegel_echo", "produces"),
    ("siegel_threefold", "moment_problem", "underlies"),
    ("rigid_cy3", "pair_28_0", "contains"),
    ("one_parameter_world", "pair_1_65", "contains"),
    ("one_parameter_world", "pair_1_101", "contains"),
    ("one_parameter_world", "pair_1_149", "contains"),
    ("cicy", "pair_1_65", "realizes"),
    ("tci_construction", "total_28", "fills"),
    ("conifold_transition", "total_66", "fills"),
    ("conifold_transition", "total_80", "fills"),
    ("free_quotient", "total_17", "fills"),
    ("free_quotient", "hua_tower", "generates"),
    ("hua_tower", "pair_1_65", "depends_on"),
    ("siegel_echo", "total_28", "related_to"),
    ("siegel_echo", "total_80", "related_to"),
    ("siegel_echo", "total_92", "related_to"),
    ("k3_fibration", "total_28", "evidence_for"),
    ("non_toric_ladders", "total_81", "evidence_for"),
    ("toric_completeness", "total_81", "contains"),
    ("toric_completeness", "total_92", "contains"),
    ("toric_completeness", "non_toric_ladders", "depends_on"),
    ("self_eigen_presentation", "total_66", "evidence_for"),
    ("self_eigen_presentation", "total_92", "evidence_for"),
    ("plankian_law", "total_hodge_number", "describes"),
    ("ml_landscape", "ks_dataset", "applied_in"),
    ("ks_gap", "total_17", "evidence_for"),
    ("self_mirror_diagonal", "total_28", "contains"),
    ("self_mirror_diagonal", "total_66", "contains"),
    ("self_mirror_diagonal", "total_80", "contains"),
    ("self_mirror_diagonal", "total_92", "contains"),
    ("self_mirror_diagonal", "pair_1_1", "contains"),
    ("self_mirror_diagonal", "pair_251_251", "contains"),
    ("weighted_p4", "pair_33_33", "realizes"),
    ("k3_fibration", "pair_33_33", "realizes"),
    # totals → pairs
    ("total_17", "pair_1_16", "contains"),
    ("total_17", "pair_4_13", "contains"),
    ("total_17", "pair_15_2", "contains"),
    ("total_28", "pair_14_14", "contains"),
    ("total_28", "pair_28_0", "contains"),
    ("total_29", "pair_1_28", "contains"),
    ("total_66", "pair_1_65", "contains"),
    ("total_66", "pair_33_33", "contains"),
    ("total_80", "pair_40_40", "contains"),
    ("total_92", "pair_46_46", "contains"),
    ("total_92", "pair_2_90", "contains"),
    ("pair_3_62", "codim4_construction", "constructed_by"),
    # papers → papers (citations)
    ("freitag_salvati_siegel", "cynk_freitag_salvati", "cites"),
    ("ccm_small_hodge", "candelas_davies", "cites"),
    ("davies_zoo", "candelas_davies", "cites"),
    ("davies_zoo", "batyrev_kreuzer_conifold", "cites"),
    ("davies_zoo", "freitag_salvati_siegel", "cites"),
    ("leontaris_shukla", "ks_classification_4d", "cites"),
]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", text.lower()).strip("_")


def build_cy3_graph(
    graph: Optional[KnowledgeGraph] = None,
    encoder: Optional[EncoderLayer] = None,
    ingest_chunks: bool = True,
    out_dir: Optional[Path] = None,
) -> tuple[KnowledgeGraph, EncoderLayer]:
    """Seed the Calabi–Yau knowledge graph. Returns (graph, encoder).

    Idempotent (skips existing nodes/edges), so it is safe to re-run. The
    graph is persisted to ``out_dir`` (default ``database/calabiyau3fold/graph_data/``) with the
    encoder index next to it in ``out_dir/vectors/index.json``.
    """
    out = Path(out_dir or CY3_OUT)
    # auto_load=True: if a graph already exists in `out`, load it first so
    # previously grown nodes/edges survive rebuilds (build is idempotent —
    # seed nodes/edges are only added when missing).
    graph = graph or KnowledgeGraph(path=out / "knowledge_graph.json", auto_load=True)
    encoder = encoder or EncoderLayer()

    # 1. Paper nodes
    for nid, name, arxiv, desc, pdf, txt in PAPERS:
        if graph.get_node(nid) is None:
            content = {"arxiv": arxiv}
            if pdf:
                content["pdf"] = str(PAPERS_DIR / pdf)
            if txt:
                content["txt"] = str(EXTRACTED_DIR / txt)
            graph.add_node(nid, name, category="paper", description=desc,
                           content=content)

    # 2. Dataset nodes
    for nid, name, desc, files in DATASETS:
        if graph.get_node(nid) is None:
            graph.add_node(
                nid, name, category="dataset", description=desc,
                content={"files": [str(DATASETS_DIR / f) for f in files]},
            )

    # 3. Concept / total / pair nodes
    for nid, name, desc in CONCEPTS:
        if graph.get_node(nid) is None:
            graph.add_node(nid, name, category="concept", description=desc)
    for nid, name, verdict in TOTALS:
        if graph.get_node(nid) is None:
            graph.add_node(nid, name, category="total",
                           description=verdict)
    for nid, name, desc in PAIRS:
        if graph.get_node(nid) is None:
            graph.add_node(nid, name, category="pair", description=desc)

    # 4. Edges
    for source, target, rel in SEED_EDGES:
        try:
            if not graph.has_edge(source, target, rel):
                graph.add_edge(source, target, relation=rel, agent_run="seed-cy3")
        except ValueError as exc:
            logger.warning("seed edge skipped: %s", exc)

    # 5. Encode the extracted paper texts (chunk → embed → index)
    if ingest_chunks:
        for nid, name, arxiv, desc, pdf, txt in PAPERS:
            if not txt:
                continue
            path = EXTRACTED_DIR / txt
            if not path.exists():
                logger.warning("missing extracted text: %s", path)
                continue
            text = path.read_text(encoding="utf-8", errors="replace").strip()
            if len(text) < 40:
                logger.warning("empty extraction: %s", path)
                continue
            encoder.ingest(nid, text, section=name, source_ref={"file": str(path)})
        for nid, node in graph._nodes.items():
            encoder.ingest_meta(nid, f"{node.entryname} {node.description}")

    # 6. Persist
    graph.pagerank()
    out.mkdir(parents=True, exist_ok=True)
    (out / "vectors").mkdir(parents=True, exist_ok=True)
    graph.save()
    encoder.save(out / "vectors" / "index.json")
    return graph, encoder


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    g, enc = build_cy3_graph()
    print(g.summary())
    print(f"chunks indexed: {enc.index.size()}")
    print(f"saved to      : {CY3_OUT}")
    print(f"export        : {export_backward_compatible(g, out_root=CY3_OUT / 'export')}")


# ══════════════════════════════════════════════════════════════════════════════
# Note-database project assets — node → file relationship
# ══════════════════════════════════════════════════════════════════════════════


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def sync_project_assets(
    graph: KnowledgeGraph,
    project_dir: Path,
    research_files: Optional[list] = None,
    force: bool = False,
) -> dict:
    """Copy every file referenced by the graph's nodes into the note project's
    ``assets/`` folder and write the **node → file relationship**:

      assets/papers/*.pdf       — paper PDFs      (role "paper")
      assets/extracted/*.txt    — pypdf texts     (role "extracted-text")
      assets/datasets/*         — KS/Davies data  (role "dataset")
      assets/research/*         — research notes  (role "research", project-level)
      assets/manifest.json      — node_id → [ {role, file, size, sha256} ]
      assets/README.md          — human-readable node ↔ file table

    ``file`` paths in the manifest are relative to ``project_dir`` (so a note
    can reference ``assets/papers/x.pdf`` and the file lives next to it).

    Returns the manifest dict.
    """
    project_dir = Path(project_dir)
    assets = project_dir / "assets"
    manifest: dict = {}
    copied = 0

    def _copy(src: Path, role: str, sub: str) -> Optional[dict]:
        nonlocal copied
        if not src.exists():
            return None
        dst = assets / sub / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        if force or not dst.exists():
            shutil.copy2(src, dst)
        copied += 1
        return {
            "role": role,
            "file": str(dst.relative_to(project_dir)),   # e.g. assets/papers/x.pdf
            "size": dst.stat().st_size,
            "sha256": _sha256(dst),
        }

    for nid, node in graph._nodes.items():
        c = node.content or {}
        entries = []
        if c.get("pdf"):
            e = _copy(Path(c["pdf"]), "paper", "papers")
            if e:
                entries.append(e)
        if c.get("txt"):
            e = _copy(Path(c["txt"]), "extracted-text", "extracted")
            if e:
                entries.append(e)
        for f in c.get("files", []):
            e = _copy(Path(f), "dataset", "datasets")
            if e:
                entries.append(e)
        if entries:
            manifest[str(nid)] = entries

    # project-level research documents (not bound to a single node)
    proj_entries = []
    for rf in research_files or []:
        e = _copy(Path(rf), "research", "research")
        if e:
            proj_entries.append(e)
    if proj_entries:
        manifest["_project"] = proj_entries

    # ── manifest.json ────────────────────────────────────────────────────
    (assets / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

    # ── README.md (human-readable relationship table) ────────────────────
    rows = []
    for nid, entries in sorted(manifest.items()):
        name = graph.get_node(nid).entryname if graph.get_node(nid) else "(project)"
        for e in entries:
            rows.append(f"| `{nid}` | {name} | `{e['role']}` | `{e['file']}` | "
                        f"{e['size']:,} B | `{e['sha256'][:12]}…` |")
    readme = (
        "# Project Assets — node ↔ file relationship\n\n"
        "Every non-Markdown file this project depends on is copied here from the\n"
        "source research folder, organized by role:\n\n"
        "| folder | role |\n|---|---|\n"
        "| `papers/` | paper PDFs |\n"
        "| `extracted/` | pypdf plain-text extractions (encoder corpus) |\n"
        "| `datasets/` | Kreuzer–Skarke / Davies / TCI data files |\n"
        "| `research/` | the research notebook + HTML export |\n\n"
        "**The authoritative mapping is `manifest.json`** (node_id → files with role, "
        "path, size, sha256). Human-readable table:\n\n"
        "| node | entryname | role | file | size | sha256 |\n"
        "|---|---|---|---|---|---|\n"
        + "\n".join(rows) + "\n"
    )
    (assets / "README.md").write_text(readme, encoding="utf-8")

    logger.info("project assets synced: %d files into %s (manifest: %d nodes)",
                copied, assets, len(manifest))
    return manifest
