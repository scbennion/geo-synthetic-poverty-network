# Minimum Viable Synthetic Network Model

This project builds a minimum viable model of people, resources, and their relationships, starting with a synthetic population and contact networks for Salt Lake County, Utah. It supports the lab's broader research into how social network structure and access to resources relate to poverty.

The immediate research questions are whether we can construct a plausible network snapshot, evaluate its structure against empirical networks, test its robustness under perturbations, and attach useful spending or resource data. Poverty-mobility interventions belong to the broader research program; they are outside this synthetic model's initial scope.

A **synthetic population** consists of artificial people assembled to match selected demographic statistics. Generated household memberships, home points, and contacts are modeled relationships, not identified residents or observed friendships.

## Current capabilities

- Prepare Census, commuting, road, and education inputs.
- Generate people, households, home locations, and work or education assignments.
- Build undirected, unweighted household, school, daycare, and workplace contact networks.
- Check demographic and spatial agreement and export a run to a Neo4j knowledge graph.

The [MVP assumptions](docs/assumptions.md) describe an intended directed, weighted, multilayer simulation model. Resource-transfer weights, individual wealth/spending, empirical friendship validation, and simulation integration are not implemented by this pipeline.

## Research questions

The broader lab questions, quoted from the professor's UDRC proposal as shared in the team's Discord discussion:

> How can available geographic, demographic, education, and economic data be used to construct synthetic networks that approximate the relationships among people and resources in specific regions?

> How do alternative assumptions about network structure—including ties among agents and connections between agents and resources—affect equity and economic outcomes in agent-based simulations?

> To what extent do the modeled economic outcomes correspond to observed outcomes in the regions represented by the source data, and what does that comparison reveal about the network designs and assumptions?

## Start with Salt Lake County

Use Python 3.12 and follow the [pipeline guide](docs/pipeline.md) for environment prerequisites, input preparation, execution, validation, and Neo4j import. The working example is Utah (`--state ut`), Salt Lake County (`--counties 035`), seed 42. After preparing its inputs, preview synthesis with:

```bash
python -m pipeline.population_synthesis.run_synthesis_by_state --state ut --counties 035 --seed 42 --dry-run
```

Data live under `data-pre-reorganization` by default, or the directory selected by `GSPN_DATA_DIR`. Data are distributed separately and ignored by Git. The pilot has known coverage and modeling limitations; a successful demographic check does not establish that generated ties match real friendships.

## Documentation

| Guide | What it covers |
| --- | --- |
| [Model assumptions](docs/assumptions.md) | Intended MVP design and future possibilities |
| [Pipeline](docs/pipeline.md) | Execution sequence and troubleshooting |
| [Architecture](docs/architecture.md) | Current processing stages and responsibilities |
| [Input data and file formats](docs/input-data.md) | Verified source references, preparation, local handoffs, and published-download differences |
| [Methods and open decisions](docs/methods.md) | Population generation, contacts, validation, and unresolved model choices |
| [Limitations](docs/limitations.md) | Current modeling constraints, implementation gaps, and potential solutions |
| [Knowledge graph](docs/knowledge-graph.md) | Neo4j schema and example queries |
| [Optimization](docs/optimization.md) | Earlier measurements, comparisons, and estimates |
| [Changelog](docs/changelog.md) | Chronological history of changes from Jiang et al. (2024) |
| [Agent guidance](docs/agents.md) | Contribution scope, readability rules, and approval requirements |

## Attribution and license

This repository adapts Jiang et al. (2024), [A large-scale geographically explicit synthetic population with social networks for the United States](https://doi.org/10.1038/s41597-024-03970-1). The original [published datasets](https://osf.io/fpnc2/) are distributed separately. Preserve attribution when using or extending the model; individual source datasets can have their own access, licensing, and citation requirements.

See [LICENSE](LICENSE) for CC0 1.0 Universal.
