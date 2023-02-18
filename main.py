#!/usr/bin/env python3

import argparse
from pathlib import Path
import requests
import datetime
import logging
import json
import time
import tqdm

PAPER_DETAILS_URL = "https://api.semanticscholar.org/graph/v1/paper/{}?fields=title,venue,year,publicationDate,publicationTypes,authors,journal,url,externalIds"
AUTHOR_DETAILS_URL = "https://api.semanticscholar.org/graph/v1/author/{}?fields=papers,papers.year"
ANTHOLOGY_TEMPLATE = "https://aclanthology.org/{}.bib"


def return_request(url: str) -> dict:
    """Returns the json response from the given url"""

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


def write(papers: list, cache_path: str):
    # eliminate duplicates
    papers = list({v["paperId"]: v for v in papers}.values())

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
    # CLSP faculty
    file_path_authors = "people.json"
    with open(file_path_authors, "r") as f:
        authors = json.load(f)

    # check if there is a file in the cache
    papers = []
    paper_ids = {}
    if Path(cache_path).exists():
        print(f"Loading papers from cache {cache_path}...")
        with open(cache_path, "r") as f:
            papers = json.load(f)
            paper_ids = { paper["paperId"]: paper for paper in papers }

    for author_name, author_info in tqdm.tqdm(authors.items()):
        s2id = author_info["s2id"]
        start_year = author_info["start_year"]
        end_year = author_info["end_year"]

        # get the papers for the author
        print(f"Processing {author_name} ({author_info})")
        papers_for_author = return_request(AUTHOR_DETAILS_URL.format(s2id))
        print(f"-> found {len(papers_for_author['papers'])} papers for {author_name}")
        for paper_dict in papers_for_author["papers"]:
            paper_id = paper_dict["paperId"]

            # make sure we only count papers during the time their authors are here

            # skip if the paper was published before the start year
            if start_year and "year" in paper_dict and paper_dict["year"] and start_year > paper_dict["year"]:
                # print("skipping paper because it was published before the start year")
                continue

            # skip if the paper was published after the end year
            if end_year and "year" in paper_dict and paper_dict["year"] and end_year < paper_dict["year"]:
                # print("skipping paper because it was published after the end year")
                continue

            # skip if we already have the paper
            paper = None
            if paper_id in paper_ids:
                paper = paper_ids[paper_id]

            if paper is None or "bibtex" not in paper:
                if paper is None:
                    print(f"-> processing new paper {paper_id}")
                elif "bibtex" not in paper:
                    print(f"-> completing bibtex for paper {paper_id}")

                paper = return_request(PAPER_DETAILS_URL.format(paper_dict["paperId"]))

                # cache the bibtex entry since it might also require a network request
                paper["bibtex"] = get_bibtex(paper)

                papers.append(paper)

        # save the cache after each author
        papers = write(papers, cache_path)


pub_template = \
"""
@inproceedings{{%s,
    title = {{{title}}},
    author = {author_list},
    year = {year},{month}
    booktitle = {{{journal}}}, 
    url = {{{url}}},
}}
"""

def get_year(cache_dict):
    if cache_dict["year"] is not None:
        year = cache_dict["year"]
    elif cache_dict["publicationDate"] is not None:
        date = datetime.datetime.strptime(cache_dict["publicationDate"], "%Y-%m-%d")
        year = date.year
    else:
        year = None
    return year


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
        logging.info(f"-> Swapping in Anthology BibTex for {url}")
        response = requests.get(url)
        if response.status_code == 200:
            cur_pub = response.text

    if cur_pub is None:
        # generate this if the Anthology call failed or there was
        # no Anthology ID
        cur_pub = pub_template.format(title=title,
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
    all_pubs = []
    # read json file
    with open(cache_path, "r") as f:
        cache = json.load(f)

    # drop duplicates from cache
    cache = list({v["paperId"]: v for v in cache}.values())

    # strip the ones with no year
    cache = [item for item in cache if get_year(item) is not None]

    # sort by year
    cache = sorted(cache, key=lambda x: get_year(x), reverse=True)

    for cache_dict in cache:
        cur_pub = cache_dict["bibtex"]
        all_pubs.append(cur_pub)

    with open("references_generated.bib", "w") as fout:
        fout.write("".join(all_pubs))

    # append the existing bib files
    bibs = pull_existing_bibfiles()
    with open("references_generated.bib", "a") as fout:
        fout.write(bibs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--cache', help='path to the paper cache jsonl file in order to update', type=str, default=None)
    parser.add_argument('-b', '--to_bib', help='path to the paper cache jsonl file in order to convert to bib file', type=str, default=None)
    args = parser.parse_args()

    if args.cache:
        update_cache(cache_path=args.cache)
    elif args.to_bib:
        convert_to_bib(cache_path=args.to_bib)
    else:
        raise Exception("Must provide either a cache path or a bib path")
