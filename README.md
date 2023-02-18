# clsp-pubs

Generates a BibTeX file with all pubs produced by CLSP faculty, where "all pubs" is determined by Semantic Scholar.

## Extending

To add faculty, add them to `people.json`.

## Usage

You can run `run_everything.sh`, which has two steps:

* Download papers missing from the cache. This also generates BibTeX entries for those papers, if they could not be obtained from the ACL Anthology

* Generate the consolidated bib file

## Credits

Daniel Khashabi
Orion Weller
Matt Post