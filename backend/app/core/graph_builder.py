import networkx as nx
import pickle

G = nx.DiGraph()

nodes = [
    "Nexus Holdings",
    "Nexus India",
    "Internal Policy", 
    "RBI KYC",
    "RBI Credit Risk",
    "Foreign Investment",
    "Apple SEC Filings",
    "Microsoft SEC Filings"
]

G.add_nodes_from(nodes)

edges = [
    # Parent company owns the subsidiary
    ("Nexus Holdings", "Nexus India", {"relation": "OWNS_SUBSIDIARY"}),
    
    # Connecting the Parent company to its rule book
    ("Nexus Holdings", "Internal Policy", {"relation": "HAS_POLICY"}),

    # Subsidiary operational boundaries
    ("Nexus India", "RBI KYC", {"relation": "GOVERNED_BY"}),
    ("Nexus India", "RBI Credit Risk", {"relation": "GOVERNED_BY"}),
    ("Nexus India", "Foreign Investment", {"relation": "GOVERNED_BY"}),

    # Market comparisons
    ("Nexus Holdings", "Apple SEC Filings", {"relation": "MARKET_BENCHMARK"}),
    ("Nexus Holdings", "Microsoft SEC Filings", {"relation": "MARKET_BENCHMARK"}),
    
    # Policy cross-reference overlays
    ("Internal Policy", "RBI KYC", {"relation": "COMPLIANCE_OVERLAYS", "remediation_target": "UBO"}),
    ("Internal Policy", "RBI Credit Risk", {"relation": "ALIGN_WITH", "exposure_target": "directors"}),
    ("Internal Policy", "Foreign Investment", {"relation": "CROSS_REFERENCES", "ceiling_usd": 1500000})
]

G.add_edges_from(edges)

with open("data/processed/knowledge_graph.pkl", "wb") as file:
    pickle.dump(G, file)

print("\nKnowledge Graph topological map successfully initialized and serialized!\n")