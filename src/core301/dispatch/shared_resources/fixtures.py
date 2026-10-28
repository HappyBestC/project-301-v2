"""Explicit engineering scene builder. Counts are inputs, never medical standards."""
from .catalog import Catalog
from .models import Resource, Location


def research_scene(counts, *, location_id='scene'):
    catalog = Catalog()
    resources = [Resource(resource_id=kind, resource_type_id=kind, unit=catalog.resources[kind][0],
                          use_mode=catalog.resources[kind][1], initial_total=count,
                          location_id=location_id, scope_kind='research_fixture')
                 for kind, count in counts.items()]
    location = Location(location_id=location_id, capabilities=frozenset(catalog.requirements),
                        permissions=frozenset(r.permission for r in catalog.requirements.values() if r.permission),
                        protected_route_available=True, receiving_environment_verified=True)
    return resources, [location]
