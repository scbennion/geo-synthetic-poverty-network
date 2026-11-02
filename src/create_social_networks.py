import networkx as nx
import numpy as np
import csv
import os
from pathlib import Path
from loguru import logger


def wp_kind(wp):
    '''Site type of each wp id: the first letter after any leading digits ('w' work, 's' school,
    'd' daycare, 'h' home). Substring checks misfire, e.g. 'wNotFound' contains 'd'.'''
    return wp.astype(str).str.extract(r'^\d*([a-z])', expand=False)


def create_edges(x, g, rng=None):
    if len(x) <= 5:
        sw = nx.complete_graph(len(x))
    else:
        sw = nx.newman_watts_strogatz_graph(len(x), 4, 0.3, seed=rng)
    sw = nx.relabel_nodes(sw, dict(zip(sw.nodes(), x.index.values)))# what's this line for?
    g.add_edges_from(sw.edges())

def create_network(people, type, seed=None):
    # seed: int for a reproducible network; each call starts a fresh stream so a
    # network file depends only on its input population and the seed
    rng = None if seed is None else np.random.default_rng(seed)
    g = nx.Graph()
    g.add_nodes_from(people.index)

    if type in ["School", "Daycare", "Work"]:
        grouped = people.groupby('wp', group_keys=False)
        grouped.apply(lambda x: create_edges(x, g, rng))

    if type == 'Household':
        grouped = people.groupby('hhold', group_keys=False)
        grouped.apply(lambda x: create_edges(x, g, rng))
    return g

def get_neighbors(x, g):
    return [n for n in g.neighbors(x)]

def to_csv(g, population, output_name):
    col1 = list(population.index)
    col2 = population.index.map(lambda x: get_neighbors(x, g))
    col2 = list(col2)
    for i in range(len(col2)):
        col2[i] = [col1[i]] + col2[i]
    with open(output_name, 'w') as f:
        writer = csv.writer(f)
        writer.writerows(col2)


def create_networks_types(population, folder_path, state_abbreviation, name=None, seed=None):
    # name: output file prefix, e.g. 'ut_c035' for a county run; defaults to the state
    name = name or state_abbreviation
    directory_path = os.path.join(folder_path, f"{state_abbreviation}/social_networks")

    # Check if the directory exists
    if not os.path.exists(directory_path):
        # Create the directory if it does not exist
        os.makedirs(directory_path)

    daycare_nx_path = os.path.join(folder_path, f"{state_abbreviation}/social_networks/{name}_daycare_network.csv")
    if not Path(daycare_nx_path).exists():
        logger.info('Creating Daycare Network')
        select_pop = population[wp_kind(population.wp) == 'd'].set_index('id').copy()
        logger.info(f"Daycare population {len(select_pop)}")

        new_network = create_network(select_pop, "Daycare", seed)
        logger.info(f"the number of edges are: " + str(len(new_network.edges())))
        to_csv(new_network, select_pop, daycare_nx_path)
        logger.info(f"Done creating Daycare Network, writing to Daycare Graph")
    else:
        logger.info('Daycare Network already exists')

    school_nx_path = os.path.join(folder_path, f"{state_abbreviation}/social_networks/{name}_school_network.csv")
    if not Path(school_nx_path).exists():
        logger.info('Creating School Network')
        select_pop = population[wp_kind(population.wp) == 's'].set_index('id').copy()
        logger.info(f"School population {len(select_pop)}")

        new_network = create_network(select_pop, "School", seed)
        logger.info(f"the number of edges are: " + str(len(new_network.edges())))
        to_csv(new_network, select_pop, school_nx_path)
        logger.info(f"Done creating School Network, writing to School Graph")
    else:
        logger.info('School Network already exists')

    hhold_nx_path = os.path.join(folder_path, f"{state_abbreviation}/social_networks/{name}_household_network.csv")
    if not Path(hhold_nx_path).exists():
        logger.info("Creating Household network...")
        logger.info(f"Population {len(population)}")
        new_network = create_network(population.set_index('id'), "Household", seed)

        logger.info("the number of edges are: " + str(len(new_network.edges())))
        to_csv(new_network, population.set_index('id'), hhold_nx_path)
        logger.info(f"Done creating Household Network, writing to Household Graph")
    else:
        logger.info('Household Network already exists')