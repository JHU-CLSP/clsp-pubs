#!/usr/bin/env python3

"""
This script provides two functions:

* Update papers cache (--cache path/to/cache.json). This will query S2 for all authors
  listed in people.json, and then query S2 for all papers for each author. Results are
  written to the cache file. If the cache file already exists, it will be loaded first,
* Update the bibfile (--bibfile path/to/bibfile.bib). This will read the cache file and
  produce a bibfile containing all papers in the cache. BibTeX is read from a "bibtex"
  field in the cache file.

BibTeX is taken from S2, but if there is an Anthology ID identifier, we query the Anthology
and get their bibtex, instead.
"""

import argparse
import requests
import datetime
import logging
import json
import time
import tqdm
import os

from pathlib import Path
from collections import OrderedDict

logging.basicConfig(level=logging.INFO)

PAPER_DETAILS_URL = "https://api.semanticscholar.org/graph/v1/paper/{}?fields=title,venue,year,publicationDate,publicationTypes,authors,journal,url,externalIds"
AUTHOR_DETAILS_URL = "https://api.semanticscholar.org/graph/v1/author/{}?fields=papers,papers.year"
ANTHOLOGY_TEMPLATE = "https://aclanthology.org/{}.bib"


def return_request(url: str) -> dict:
    """Returns the json response from the given url.
    
    :param url: The URL to query
    :return: The JSON response
    """

    attempt_no = 1
    sleep_time = 1
    while attempt_no < 10:
        response = requests.get(url)

        if response.status_code == 200:
            break
        elif response.status_code == 429:
            sleep_time = 2 ** attempt_no
            print(f"-> Got status code {response.status_code}, retrying in {sleep_time} seconds")
            time.sleep(sleep_time)
        else:
            print(f"-> Got status code {response.status_code}, retrying in {sleep_time} seconds")
            time.sleep(0.5)

        attempt_no += 1
    else:
        raise Exception("Could not get a response from the server after {attempt_no} attempts")

    time.sleep(0.5)
    data = response.json()
    return data


def write(paper_cache: OrderedDict, cache_path: str):
    """Write papers to the JSON disk cache.

    :param papers: The list of papers.
    :param cache_path: The path to the file containing the cache.
    :return: The papers, with duplicates removed.
    """
    papers = [paper for paper in paper_cache.values()]

    # write the papers to a json file
    with open(cache_path, "w") as f:
        json.dump(papers, f, indent=4)

    return papers


def pull_existing_bibfiles():
    bibfile = [
        "https://www.cs.jhu.edu/~jason/papers/bibtex.bib"
    ]
    bibs = ""
    for url in bibfile:
        # download the bibfile if it exists
        response = requests.get(url)
        if response.status_code == 200:
            bibs += response.text
        else:
            print("Could not find bibfile at {0}".format(url))
    return bibs


def update_cache(cache_path: str):
    """
    Main function. Writes crawled database to {cache_path}. If
    the cache path exists, it will be loaded first, and then updated.
    """

    # CLSP faculty
    file_path_authors = "people.json"
    with open(file_path_authors, "r") as f:
        authors = json.load(f)

    # The list of papers. These will be read from the cache (if existent),
    # updated, and then written to disk
    paper_cache = OrderedDict()

    # Papers that have been seen. We use this to remove papers found in the
    # cache that were not found among the papers for any CLSP authors
    seen_papers = set()

    # load the cache if present
    if Path(cache_path).exists():
        print(f"Loading papers from cache {cache_path}...")
        with open(cache_path, "r") as f:
            json_data = json.load(f)
            for paper_dict in json_data:
                paper_id = paper_dict["paperId"]
                paper_cache[paper_id] = paper_dict

    for author_name, author_info in tqdm.tqdm(authors.items()):
        s2id = author_info["s2id"]
        start_year = author_info["start_year"]
        end_year = author_info["end_year"]

        # get the papers for the author
        logging.info(f"Processing {author_name} (id={s2id}, {start_year or ''}-{end_year or ''})")
        papers_for_author = return_request(AUTHOR_DETAILS_URL.format(s2id))
        logging.info(f"-> found {len(papers_for_author['papers'])} papers for {author_name}")
        for paper_dict in papers_for_author["papers"]:
            paper_id = paper_dict["paperId"]

            # Make sure we only count papers during the time their authors are here.
            # - skip if the paper was published before the start year
            if start_year and "year" in paper_dict and paper_dict["year"] and start_year > paper_dict["year"]:
                # print("skipping paper because it was published before the start year")
                continue

            # - skip if the paper was published after the end year
            if end_year and "year" in paper_dict and paper_dict["year"] and end_year < paper_dict["year"]:
                # print("skipping paper because it was published after the end year")
                continue

            # mark the paper as seen
            seen_papers.add(paper_id)

            # fetch the paper object from the cache...
            paper_dict = None
            if paper_id in paper_cache:
                paper_dict = paper_cache[paper_id]

            else:
                # ...or get its details from S2
                logging.info(f"-> processing new paper {paper_id}")

                paper_dict = return_request(PAPER_DETAILS_URL.format(paper_id))

                paper_cache[paper_id] = paper_dict

            # Create thte bibtex entry if it doesn't exist
            if "bibtex" not in paper_dict:
                logging.info(f"-> completing bibtex for paper {paper_id}")

                # cache the bibtex entry since it might also require a network request
                paper_dict["bibtex"] = get_bibtex(paper_dict)

        # Save the cache after each author. It will get updated again outside the loop
        # removing papers that were not found for any author
        write(paper_cache, cache_path)

    # Remove papers no longer associated with an author
    paper_ids = list(paper_cache.keys())
    for paper_id in paper_ids:
        if paper_id not in seen_papers:
            title = paper_cache[paper_id]["title"]
            logging.info(f"Removing paper {paper_id} from cache ({title})")
            paper_cache.pop(paper_id)

    # and write to disk
    write(paper_cache, cache_path)


def get_year(cache_dict):
    if cache_dict["year"] is not None:
        year = cache_dict["year"]
    elif cache_dict["publicationDate"] is not None:
        date = datetime.datetime.strptime(cache_dict["publicationDate"], "%Y-%m-%d")
        year = date.year
    else:
        year = None
    return year


PUB_TEMPLATE = \
    """
    @inproceedings{{%s,
        title = {{{title}}},
        author = {author_list},
        year = {year},{month}
        booktitle = {{{journal}}}, 
        url = {{{url}}},
    }}
    """


def get_bibtex(cache_dict):
    """Generates or retrieves the bibtex entry for the paper

    :param cache_dict: A dictionary of paper metadata obtained from S2.
    :return: The BibTeX text.
    """
    title = cache_dict["title"]
    journal = cache_dict["venue"]
    if journal == "" and cache_dict["journal"] is not None and "name" in cache_dict["journal"]:  # maybe a journal
        journal = cache_dict["journal"]["name"]
        # print(journal)

    url = cache_dict["url"]

    year = get_year(cache_dict)

    if cache_dict["publicationDate"] is not None:
        date = datetime.datetime.strptime(cache_dict["publicationDate"], "%Y-%m-%d")
        month = date.month
    else:
        month = None

    author_list = "{" + " and ".join(["{" + item["name"] + "}" for item in cache_dict["authors"]]) + "}"
    ident = cache_dict["externalIds"]["CorpusId"]

    cur_pub = None
    if "ACL" in cache_dict["externalIds"]:
        # Use the Anthology BibTeX if this is a *ACL paper
        anthology_id = cache_dict["externalIds"]["ACL"]
        url = ANTHOLOGY_TEMPLATE.format(anthology_id)

        # download the file
        logging.info(f"-> swapping in Anthology BibTex for {url}")
        response = requests.get(url)
        if response.status_code == 200:
            cur_pub = response.text

    if cur_pub is None:
        # generate this if the Anthology call failed or there was
        # no Anthology ID
        cur_pub = PUB_TEMPLATE.format(title=title,
                                      author_list=author_list,
                                      year=year,
                                      month="\n\tmonth = {%s}," % month if month is not None else "",
                                      journal=journal,
                                      url=url) % ident

    return cur_pub


def convert_to_bib(cache_path: str):
    """Converts the papers.json file to a bibtex file

    :param cache_path: path to the papers.json file    
    """
    # read json file
    with open(cache_path, "r") as f:
        cache = json.load(f)

        # drop duplicates from cache
        cache = list({v["paperId"]: v for v in cache}.values())

        # strip the ones with no year
        cache = [item for item in cache if get_year(item) is not None]

        # sort by year
        cache = sorted(cache, key=lambda x: get_year(x), reverse=True)

        with open("references_generated.bib", "w") as fout:
            for paper_dict in cache:
                bib = paper_dict["bibtex"]
                print(bib.rstrip(), file=fout)

        # append pre-existing bib files
        bibs = pull_existing_bibfiles()
        with open("references_generated.bib", "a") as fout:
            print(bibs, file=fout)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-r', '--reset', help='whether to reset the cache', action='store_true')
    parser.add_argument('-c', '--cache', help='path to the paper cache jsonl file in order to update',
                        type=str, default=None)
    parser.add_argument('-b', '--to_bib', help='path to the paper cache jsonl file in order to convert to bib file',
                        type=str, default=None)
    args = parser.parse_args()

    if args.cache:
        if args.reset:
            # replace `args.cache` file with an empty file
            with open(args.cache, "w") as f:
                pass
        update_cache(cache_path=args.cache)
    elif args.to_bib:
        convert_to_bib(cache_path=args.to_bib)
    else:
        raise Exception("Must provide either a cache path or a bib path")
