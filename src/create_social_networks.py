"""Generate undirected contacts within households and daytime sites."""
import csv
from pathlib import Path

import networkx as nx
import numpy as np
from loguru import logger


def wp_kind(wp):
    """First site letter after leading digits: w=work, s=school, d=daycare, h=home.

    Substring checks misclassify workplace IDs such as ``wNotFound`` as daycare.
    """
    return wp.astype(str).str.extract(r'^\d*([a-z])', expand=False)


def create_edges(people, graph, rng=None):
    if len(people) <= 5:
        contacts = nx.complete_graph(len(people))
    else:
        contacts = nx.newman_watts_strogatz_graph(len(people), 4, 0.3, seed=rng)
    # The generator numbers nodes from zero; use the actual person IDs in the output.
    contacts = nx.relabel_nodes(contacts, dict(zip(contacts.nodes(), people.index)))
    graph.add_edges_from(contacts.edges())


def create_network(people, type, seed=None):
    """Build one contact setting, retaining isolated people and input node order.

    Each call starts a fresh random stream, so cached settings cannot affect the
    remaining settings. Group order determines which groups receive which draws.
    """
    rng = None if seed is None else np.random.default_rng(seed)
    graph = nx.Graph()
    graph.add_nodes_from(people.index)
    if type in ('School', 'Daycare', 'Work'):
        group_column = 'wp'
    elif type == 'Household':
        group_column = 'hhold'
    else:
        return graph

    for _, group in people.groupby(group_column, sort=True):
        create_edges(group, graph, rng)
    return graph


def to_csv(graph, population, output_name):
    """Write headerless adjacency rows in population and neighbor insertion order."""
    rows = [[person, *graph.neighbors(person)] for person in population.index]
    with open(output_name, 'w') as stream:
        csv.writer(stream).writerows(rows)


def create_networks_types(population, folder_path, state_abbreviation, name=None, seed=None):
    """Write daycare, school, and household networks, leaving existing files intact."""
    name = name or state_abbreviation
    directory = Path(folder_path) / state_abbreviation / 'social_networks'
    directory.mkdir(parents=True, exist_ok=True)

    for kind, site_letter in (('Daycare', 'd'), ('School', 's'), ('Household', None)):
        path = directory / f'{name}_{kind.lower()}_network.csv'
        if path.exists():
            logger.info(f'{kind} Network already exists')
            continue

        selected = (population if site_letter is None
                    else population[wp_kind(population.wp) == site_letter])
        people = selected.set_index('id').copy()
        logger.info(f'Creating {kind} Network for {len(people)} people')
        graph = create_network(people, kind, seed)
        to_csv(graph, people, path)
        logger.info(f'Wrote {kind} Network: {graph.number_of_edges()} edges')
