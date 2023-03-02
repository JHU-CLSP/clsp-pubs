# clsp-pubs

Generates a BibTeX file with all pubs produced by CLSP faculty, where "all pubs" is determined by Semantic Scholar.

## Extending

To add faculty, add them to `people.json`.

## Usage

You can run `run_everything_*.sh`, which has two steps:

* Download papers missing from the cache. This also generates BibTeX entries for those papers, if they could not be obtained from the ACL Anthology

* Generate the consolidated bib file


Running [`run_everything_reset_cache.sh`](run_everything_reset_cache.sh) would reset the existing cache (as opposed to updating it). 
This often what we'd like to run in practice since it collects the latest paper names, published venues or author name conventions. This may take up an hour to finish.  
The other script [`run_everything_update_existing_cache.sh`](run_everything_update_existing_cache.sh) is also handy when debugging since it can finish in under 2-3 minutes.  

## Credits

Daniel Khashabi, 
Orion Weller,
Matt Post