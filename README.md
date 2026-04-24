# wsusscn2-knowledge-graph

[![GitHub stars](https://img.shields.io/github/stars/JolanB110/wsusscn2-knowledge-graph)](https://github.com/JolanB110/wsusscn2-knowledge-graph)
[![Python](https://img.shields.io/badge/python-3.11-blue)](https://www.python.org/)
[![Status](https://img.shields.io/badge/status-in%20progress-orange)]()

## Overview

**wsusscn2-knowledge-graph** is a research project that builds a structured knowledge graph from the Microsoft Windows Update offline catalog (`wsusscn2.cab`).

The catalog contains metadata for over **136,000 Windows updates** distributed across 75 packages in XML format. This project extracts, models, and stores this data as a knowledge graph to enable structured querying of patch metadata, security vulnerabilities, update dependencies, and product relationships.

> Internship project at **ERIC Laboratory, Université Lyon 2** (April – June 2026).

---

## Data Source

The `wsusscn2.cab` file is the Microsoft Windows Update offline scan file, publicly available from Microsoft's servers. It contains metadata for more than **136,270 updates** distributed across more than **74 packages**.

### Catalog Structure

Each package exposes up to 6 data sources, all linked by a `RevisionId` key:

| Source | Content | Status |
|---|---|---|
| `package/package.xml` | Global structure, relations, identifiers | ✅ Explored |
| `/x/` | Technical metadata (KB, severity, product version) | ✅ Explored |
| `/l/en/` | Human-readable titles and descriptions | ✅ Explored |
| `/c/` | Complementary configuration data | ✅ Explored |
| `/files/` | Annexe files | 🔄 Not yet explored |
| `/e/` | EULA files | 🔄 Not yet explored |

---

## Graph Model (V1 - in progress)

### Nodes

| Node | Source | Instances |
|---|---|---|
| `Update` | package.xml | 136,271 |
| `Product` | package.xml > Categories | 199 |
| `ProductFamily` | package.xml > Categories | 38 |
| `Company` | package.xml > Categories | 1 |
| `UpdateClassification` | package.xml > Categories | 5 |
| `KBArticle` | /x/ | — |
| `Severity` | /x/ | 4 values |

### Relations

| Relation | From | To | Source field |
|---|---|---|---|
| `DEPENDS_ON` | Update | Update | Prerequisites |
| `BELONGS_TO` | Update | Product / ProductFamily / Company / UpdateClassification | Categories |
| `SUPERSEDED_BY` | Update | Update | SupersededBy |
| `BUNDLED_BY` | Update | Update | BundledBy |
| `REFERENCED_AS` | Update | KBArticle | KBArticleID |
| `HAS_SEVERITY` | Update | Severity | MsrcSeverity |

---

## Installation

```bash
git clone https://github.com/JolanB110/wsusscn2-knowledge-graph.git
cd wsusscn2-knowledge-graph
pip install lxml neo4j
```

> The `wsusscn2.cab` file is not included in this repository.  
> Download it from Microsoft's servers and extract it into a local directory with this link : (iwr https://wsusscn2.cab -OutFile wsusscn2.cab) or (curl.exe -L https://wsusscn2.cab -o wsusscn2.cab)

---

## Configuration
Before running any script, set the `WSUS_DIR` environment variable to your local wsusscn2 extraction path:

**Windows:**
set WSUS_DIR=C:\path\to\wsusscn2

**Linux/macOS:**
export WSUS_DIR=/path/to/wsusscn2

## Tech Stack

- **Python 3.11** — data extraction and preprocessing (`lxml`, `neo4j` driver)
- **BaseX 12.2** — XQuery-based XML exploration
- **Graph database** — TBD (Neo4j or equivalent)

---

## Progress

- [x] Phase 1 — Data exploration and inventory
- [x] Phase 2 — Python parsing pipeline (in progress)
- [x] Phase 3 — Graph model validation (in progress)
- [ ] Phase 4 — Graph database import
- [ ] Phase 5 — Visualization and querying

---

## References

- [Microsoft WSUS Offline Scan File documentation](https://support.microsoft.com/en-us/topic/detailed-information-for-developers-who-use-the-windows-update-offline-scan-file-51db1d9e-038b-0b15-16e7-149aba45f295)
- [Neo4j documentation](https://neo4j.com/docs/getting-started/)
- [Neo4j Python driver](https://neo4j.com/docs/python-manual/current/)
- [BaseX documentation](https://docs.basex.org)
