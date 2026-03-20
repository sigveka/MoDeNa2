"""Cytoscape dependency graph for substituteModels."""
import dash_cytoscape as cyto
from dash import html
from urllib.parse import quote


def _collect_nodes_edges(model, depth: int = 0, max_depth: int = 3,
                          visited: set | None = None):
    """Recursively collect Cytoscape nodes and edges up to max_depth."""
    if visited is None:
        visited = set()

    nodes = []
    edges = []

    if model._id in visited or depth > max_depth:
        return nodes, edges

    visited.add(model._id)
    nodes.append({'data': {'id': model._id, 'label': model._id}})

    for sub in getattr(model, 'substituteModels', []):
        edges.append({'data': {'source': model._id, 'target': sub._id}})
        sub_nodes, sub_edges = _collect_nodes_edges(
            sub, depth + 1, max_depth, visited
        )
        nodes.extend(sub_nodes)
        edges.extend(sub_edges)

    return nodes, edges


def make_dependency_graph(model):
    """Return a dash_cytoscape graph of model dependencies."""
    nodes, edges = _collect_nodes_edges(model)

    if len(nodes) <= 1:
        return html.Div("No substitute models.", className="text-muted")

    elements = nodes + edges

    return cyto.Cytoscape(
        id='dependency-graph',
        layout={'name': 'breadthfirst', 'directed': True},
        style={'width': '100%', 'height': '300px'},
        elements=elements,
        stylesheet=[
            {
                'selector': 'node',
                'style': {
                    'label': 'data(label)',
                    'background-color': '#0d6efd',
                    'color': '#fff',
                    'text-valign': 'center',
                    'text-halign': 'center',
                    'font-size': '12px',
                    'width': 'label',
                    'height': 'label',
                    'padding': '8px',
                    'shape': 'roundrectangle',
                },
            },
            {
                'selector': 'edge',
                'style': {
                    'curve-style': 'bezier',
                    'target-arrow-shape': 'triangle',
                    'line-color': '#6c757d',
                    'target-arrow-color': '#6c757d',
                },
            },
        ],
    )
