#!/bin/bash

# updates the cache of papers. Should not take more than a minute
python3 main.py --cache papers.json --reset

# converts the cache to a bibtex file
python3 main.py --to_bib papers.json
