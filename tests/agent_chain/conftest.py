import pytest

from core301.dispatch.minimal import api
from core301.agent_chain.scheduling import REPLAY_PATH


@pytest.fixture(autouse=True)
def no_real_models(monkeypatch):
    import openai

    def forbidden(*args, **kwargs):
        raise AssertionError('Agent-chain tests must never make real model requests')

    monkeypatch.setattr(openai, 'OpenAI', forbidden)
    monkeypatch.setattr(openai, 'AsyncOpenAI', forbidden)


@pytest.fixture
def chain_data():
    resources, mapping = api.load_config()
    cases = api.load_cases()
    context = api.build_input(resources, mapping, cases, horizon_min=120.0, observation_time_min=60.0)
    return cases, mapping, context, api.read(REPLAY_PATH)
