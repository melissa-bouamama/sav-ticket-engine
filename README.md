# Support ticket engine in pure Python

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

*Version française : [README.fr.md](README.fr.md)*

An after sales support tool for a fictional online plant shop. It turns a messy stream of customer tickets into something a support team can act on: clean the data, rank tickets by urgency, undo mistakes, search by word, and split the work between advisors. The core algorithms are written by hand with only the standard library (no pandas, no heapq, no bisect). Each one is tested against a reference implementation and benchmarked.

> The code, the identifiers and the detailed docs are in French, the original working language. This README is the English entry point. All data in the repository is synthetic.

## What is inside

| Module | What it does | Key idea | Complexity |
|---|---|---|---|
| `ingestion.py` | Reads tickets (JSON Lines) and advisors (CSV) | Never crashes. Repairs what can safely be repaired, flags every guess, rejects the rest with a line number and a reason | O(n) |
| `file_priorite.py` | Priority queue | Handwritten binary min heap with an arrival counter, so equal priorities leave in arrival order | add and pop O(log n), peek O(1) |
| `historique.py` | Undo and redo | Command pattern with two stacks. A new action clears the redo stack in O(1) | everything O(1) |
| `index.py` | Full text search | Inverted index, from each word to the set of ticket ids. AND starts from the smallest set. Prefix search uses a handwritten binary search over a sorted vocabulary | AND about O(smallest set), prefix O(log V + r) |
| `affectation.py` | Splits tickets between advisors | Greedy strategy (most urgent first, then the least loaded skilled advisor) against a naive first come baseline. One function measures the share of deadlines met | O(n log n + n·m) |
| `pseudonymisation.py` | Privacy | Masks emails and phone numbers, replaces the client id with a salted SHA256 pseudonym | O(text length) |
| `cli.py` | Command line: `python -m moteur_sav` | Commands `bilan`, `urgents`, `chercher`, `prefixe`, `repartir` | n/a |

## Quick start

```bash
git clone <URL of this repository> && cd sav-ticket-engine
pip install -r requirements.txt     # pytest, matplotlib, streamlit (the core package needs none of them)
python -m pytest                    # 186 tests

python -m moteur_sav bilan                       # 2 439 usable tickets, 61 rejected, and why
python -m moteur_sav urgents -n 5                # the 5 most urgent open tickets
python -m moteur_sav chercher "pot cassé"        # AND search (add --mode OU for OR)
python -m moteur_sav prefixe cochen              # words starting with "cochen", here cochenilles
python -m moteur_sav repartir                    # greedy against naive assignment on the 28 September backlog

streamlit run demo/app.py                        # interactive demo, one tab per question
```

A dataset of 25 000 tickets can be generated (seeded, so reproducible). The tests, the demo and the benchmarks pick it up automatically:

```bash
python scripts/generer_donnees.py --n 25000 --sortie donnees/tickets.jsonl
```

## Results

Measured on the committed synthetic sample and on generated corpora. The scripts are in `benchmarks/` and the charts in `benchmarks/resultats/`.

Priority queue, n pushes then n pops, best of 3:

| n | heapq (C) | handwritten heap | list sorted again on each insert |
|---|---|---|---|
| 1 000 | 0.3 ms | 1.7 ms | 6.6 ms |
| 10 000 | 5 ms | 25 ms | 671 ms |
| 100 000 | 0.17 s | 0.53 s | not measured (minutes) |

The pure Python heap stays 3 to 6 times behind the C one but scales the same way. The list sorted again on each insert is O(n²) and unusable.

Inverted index against scanning every ticket, with 100 000 tickets: a two word AND query is 279 times faster. Prefix search with the handwritten binary search is 177 times faster than scanning the vocabulary. Sorting the vocabulary again on every call would cost 13.9 ms instead of 6.5 µs.

Greedy against naive assignment, on the sample backlog of 163 tickets (start on 1 October at 08:00, 20 minutes per ticket): the greedy strategy meets 81.6 % of deadlines, which is the maximum reachable because 30 tickets were already late at the start. The naive strategy meets 79.1 %. The greedy one also balances the load, with 10 to 19 tickets per advisor instead of 0 to 40. The notebook `demo/demo_repartition.ipynb` explores a variant that serves the savable tickets first.

Ingestion on the 2 500 line sample: 2 439 tickets kept and 61 rejected (19 truncated JSON, 19 missing field, 16 duplicate id, 7 invalid date). Every rule and its reason are in [docs/nettoyage.md](docs/nettoyage.md).

## Design choices worth a look

- Reject only when repairing would mean inventing data. A missing priority becomes P3 and is flagged. An unreadable one becomes P4, so it never passes ahead of real P1 tickets. A duplicate id with different content is kept under a new id.
- Original files are never modified. The loader works on a read only copy, and a SHA256 fingerprint proves the original is untouched.
- Urgency is one comparable key: deadline, then priority, then creation date. The heap, the greedy assignment and the demo all agree on it.
- No raw message is ever displayed by the demo, the command line or the test reports. Only the id, the category, the priority, the deadline and the subject are shown.
- The tests try to break the code: the heap against heapq on 10 000 random operations, the index against a naive scan on 500 queries, random undo and redo sequences, SLA rates computed by hand, and a syntax tree check that heapq and bisect are never imported. Details are in [docs/tests.md](docs/tests.md).

## Layout

```
moteur_sav/      the package (standard library only)
tests/           186 tests, one file per module plus demo, command line and benchmark checks
benchmarks/      reproducible measurements and their charts
demo/            Streamlit app, its computations, and a notebook
scripts/         seeded generator of synthetic data
donnees/         small synthetic samples (the full dataset is generated, not committed)
docs/            cleaning rules and testing notes, in French
```

## Limits and next steps

- No stemming: "cassé" and "cassée" are two different words. Use prefix search or the OR mode.
- The greedy assignment serves already late tickets first. The notebook shows a variant that avoids this, but it is not in the module yet.
- Pseudonymisation catches emails and phone numbers, not names written in free text. That would need named entity recognition.

## License

MIT, see [LICENSE](LICENSE).
