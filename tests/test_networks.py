"""Contact generation, output ordering, and cache behavior."""
import networkx as nx
import pandas as pd
import pytest

from create_social_networks import create_network, create_networks_types, to_csv


@pytest.mark.parametrize('size', [0, 1, 5])
@pytest.mark.parametrize('kind, column', [('Household', 'hhold'), ('School', 'wp'),
                                         ('Daycare', 'wp'), ('Work', 'wp')])
def test_small_groups_and_isolated_people(size, kind, column):
    ids = [f'p{i}' for i in range(size)]
    people = pd.DataFrame({column: ['site'] * size}, index=ids)
    graph = create_network(people, kind, seed=42)
    assert list(graph.nodes) == ids
    assert graph.number_of_edges() == size * (size - 1) // 2
    assert not graph.is_directed()
    assert not list(nx.selfloop_edges(graph))


def test_captured_small_world_edges_and_neighbor_order():
    people = pd.DataFrame({'wp': ['w1'] * 7}, index=[f'p{i}' for i in range(7)])
    graph = create_network(people, 'Work', seed=42)
    assert list(graph.edges()) == [
        ('p0', 'p1'), ('p0', 'p6'), ('p0', 'p2'), ('p0', 'p5'), ('p0', 'p4'),
        ('p1', 'p2'), ('p1', 'p3'), ('p1', 'p6'), ('p1', 'p4'),
        ('p2', 'p3'), ('p2', 'p4'), ('p2', 'p5'), ('p3', 'p4'), ('p3', 'p5'),
        ('p4', 'p5'), ('p4', 'p6'), ('p5', 'p6'),
    ]
    assert list(graph.neighbors('p1')) == ['p0', 'p2', 'p3', 'p6', 'p4']


def test_csv_preserves_population_and_neighbor_order(tmp_path):
    graph = nx.Graph()
    graph.add_nodes_from(['isolated', 'b', 'a', 'c'])
    graph.add_edges_from([('b', 'c'), ('b', 'a')])
    people = pd.DataFrame(index=['isolated', 'b', 'c', 'a'])
    path = tmp_path / 'network.csv'
    to_csv(graph, people, path)
    assert path.read_bytes() == b'isolated\r\nb,c,a\r\nc,b\r\na,b\r\n'


@pytest.mark.parametrize('size', [5, 6])
def test_groups_never_connect_to_other_sites(size):
    people = pd.DataFrame({'wp': ['z'] * size + ['a', None]},
                          index=[f'p{i}' for i in range(size + 2)])
    graph = create_network(people, 'Work', seed=42)
    assert set(graph.nodes) == set(people.index)
    assert graph.degree[f'p{size}'] == graph.degree[f'p{size + 1}'] == 0
    assert all(people.at[a, 'wp'] == people.at[b, 'wp'] for a, b in graph.edges())
    assert graph.number_of_edges() == (10 if size == 5 else 14)


def test_type_outputs_skip_cached_files_without_changing_other_networks(tmp_path):
    people = pd.DataFrame({
        'id': [f'p{i}' for i in range(16)],
        'hhold': ['h1'] * 8 + ['h2'] * 8,
        'wp': ['49d0'] * 7 + ['49s0'] * 7 + ['49035wNotFound', 'h2'],
    })
    complete, partial = tmp_path / 'complete', tmp_path / 'partial'
    create_networks_types(people, complete, 'ut', name='ut_c035', seed=42)
    folder = partial / 'ut' / 'social_networks'
    folder.mkdir(parents=True)
    cached = folder / 'ut_c035_daycare_network.csv'
    cached.write_bytes(b'existing output\n')
    create_networks_types(people, partial, 'ut', name='ut_c035', seed=42)
    assert cached.read_bytes() == b'existing output\n'
    for kind in ('school', 'household'):
        filename = f'ut_c035_{kind}_network.csv'
        assert (folder / filename).read_bytes() == (
            complete / 'ut' / 'social_networks' / filename).read_bytes()
    daycare = (complete / 'ut' / 'social_networks' / 'ut_c035_daycare_network.csv').read_text()
    assert 'p14' not in daycare  # wNotFound must not match daycare's 'd'.
    before = {path.name: path.read_bytes() for path in folder.iterdir()}
    create_networks_types(people, partial, 'ut', name='ut_c035', seed=7)
    assert {path.name: path.read_bytes() for path in folder.iterdir()} == before
