"""LangGraph wiring. Decisions and execution live in independently testable nodes."""
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from .nodes import Nodes, Providers
from .state import ChainState


def after_treatment(state):
    return 'build_timeline' if state['treatment_stage'] == 'failed' else 'build_dispatch_input'


def after_validation(state):
    if state['status'] == 'aborted':
        return END
    if state.get('schedule_stage') == 'failed':
        return 'build_timeline'
    return 'build_timeline' if state['accepted_schedule'] is not None else 'schedule'


def build_graph(providers: Providers, config: dict, progress: dict | None = None) -> CompiledStateGraph:
    nodes = Nodes(providers, config, progress)
    graph = StateGraph(ChainState)
    for name in ('load_scenario', 'treatment', 'build_dispatch_input', 'schedule',
                 'validate', 'build_timeline', 'execute', 'evaluate'):
        graph.add_node(name, getattr(nodes, name))
    graph.add_edge(START, 'load_scenario')
    graph.add_edge('load_scenario', 'treatment')
    graph.add_conditional_edges('treatment', after_treatment, ['build_dispatch_input', 'build_timeline'])
    graph.add_edge('build_dispatch_input', 'schedule')
    graph.add_edge('schedule', 'validate')
    graph.add_conditional_edges('validate', after_validation, ['build_timeline', 'schedule', END])
    graph.add_edge('build_timeline', 'execute')
    graph.add_edge('execute', 'evaluate')
    graph.add_edge('evaluate', END)
    # Reserved, not implemented in V1: schedule -> treatment when no candidate fits.
    # Reserved, not implemented in V1: execute -> treatment for event-driven decisions.
    return graph.compile()
