import argparse
import requests
import datetime
import json
import time
import tqdm

PAPER_DETAILS_URL = "https://api.semanticscholar.org/graph/v1/paper/REPLACE_ME?fields=title,venue,year,publicationDate,publicationTypes,authors,journal,url,externalIds"
AUTHOR_DETAILS_URL = "https://api.semanticscholar.org/graph/v1/author/REPLACE_ME?fields=papers,papers.year"


def return_request(request_type: str, request_id: int, first_attempt: bool = True) -> dict:
    print(f"Making request type {request_type} with id {request_id}, first_attempt={first_attempt}")

    if request_id is None:
        raise Exception("Request id for {request_type} is None".format(request_type=request_type))

    request_id = str(request_id)

    if request_type == "paper":
        response = requests.get(PAPER_DETAILS_URL.replace("REPLACE_ME", request_id))
    elif request_type == "author":
        response = requests.get(AUTHOR_DETAILS_URL.replace("REPLACE_ME", request_id))

    if response.status_code != 200:
        if first_attempt:
            print("Error in request, got status code {0}".format(response.status_code))
            time.sleep(60*5 + 30)
            return return_request(request_type, request_id, first_attempt=False)
        else:
            raise Exception(response)

    time.sleep(1.1)
    data = response.json()
    return data

def write(papers: list):
    # eliminate duplicates
    papers = list({v["paperId"]: v for v in papers}.values())

    # write the papers to a json file
    with open("papers.json", "w") as f:
        json.dump(papers, f, indent=4)

    return papers


def update_cache(cache_path: str):

    # CLSP faculty
    file_path_authors = "authors.json"
    with open(file_path_authors, "r") as f:
        authors = json.load(f)

    # check if there is a file in the cache
    try:
        with open(cache_path, "r") as f:
            papers = json.load(f)
            paper_ids = [paper["paperId"] for paper in papers]
    except FileNotFoundError:
        papers = []
        paper_ids = {}

    for author_name, author_info in tqdm.tqdm(authors.items()):
        s2id = author_info["s2id"]
        start_year = author_info["start_year"]
        end_year = author_info["end_year"]

        # get the papers for the author
        papers_for_author = return_request("author", s2id)
        for paper_dict in papers_for_author["papers"]:
            # make sure we only count papers during their time here

            print("paper_dict", paper_dict)
            # skip if the paper was published before the start year
            if start_year and "year" in paper_dict and paper_dict["year"] and start_year > paper_dict["year"]:
                # print("skipping paper because it was published before the start year")
                continue

            # skip if the paper was published after the end year
            if end_year and "year" in paper_dict and paper_dict["year"] and end_year < paper_dict["year"]:
                # print("skipping paper because it was published after the end year")
                continue

            # skip if we already have the paper
            if paper_dict["paperId"] in paper_ids:
                # print("skipping paper because we already have it")
                continue
            else:
                paper_details = return_request("paper", paper_dict["paperId"])

            papers.append(paper_details)
        papers = write(papers)

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

def convert_to_bib(cache_path: str):
    all_pubs = []
    # read json file
    with open(cache_path, "r") as f:
        cache = json.load(f)

    # drop duplicates from cache
    cache = list({v["paperId"]: v for v in cache}.values())

    for cache_dict in cache:
        title = cache_dict["title"]
        journal = cache_dict["venue"]
        if journal == "" and cache_dict["journal"] is not None and "name" in cache_dict["journal"]:  # maybe a journal
            journal = cache_dict["journal"]["name"]
            # print(journal)

        url = cache_dict["url"]

        year = cache_dict["year"]
        if cache_dict["publicationDate"] is not None:
            date = datetime.datetime.strptime(cache_dict["publicationDate"], "%Y-%m-%d")
            month = date.month
        else:
            month = None

        author_list = "{" + " and ".join(["{" + item["name"] + "}" for item in cache_dict["authors"]]) + "}"
        ident = cache_dict["externalIds"]["CorpusId"]


        # allow easy access to correct a bibtex, should it be wrong
        # if cache_key in corrections_dict:  # rely on semantic scholar paper id
        #     updated_cache = corrections_dict[cache_key]
        #     title, author_list, year, journal, publicationDate = updated_cache["title"], updated_cache["author_list"], \
        #     updated_cache["year"], updated_cache["journal"], updated_cache["publicationDate"]
        #     if publicationDate is not None:
        #         date = datetime.datetime.strptime(cache_dict["publicationDate"], "%Y-%m-%d")
        #         month = date.month

        cur_pub = pub_template.format(title=title,
                                      author_list=author_list,
                                      year=year,
                                      month="\n\tmonth = {%s}," % month if month is not None else "",
                                      journal=journal,
                                      url=url) % ident
        all_pubs.append(cur_pub)

    with open("references_generated.bib", "w") as fout:
        fout.write("".join(all_pubs))


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
