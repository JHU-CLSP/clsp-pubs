import requests
import os
import json
import time
from datetime import date
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

    time.sleep(0.7)
    data = response.json()
    return data

def write(papers: list):
    # eliminate duplicates
    papers = list({v["paperId"]: v for v in papers}.values())

    # write the papers to a json file
    with open("papers.json", "w") as f:
        json.dump(papers, f, indent=4)

    return papers

def extract_papers(file_path_authors: str):
    # read the json file

    with open(file_path_authors, "r") as f:
        authors = json.load(f)

    papers = []

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
                print("skipping paper because it was published before the start year")
                continue

            # skip if the paper was published after the end year
            if end_year and "year" in paper_dict and paper_dict["year"] and end_year < paper_dict["year"]:
                print("skipping paper because it was published after the end year")
                continue

            paper_details = return_request("paper", paper_dict["paperId"])
            # 3 years locked

            papers.append(paper_details)
        papers = write(papers)

if __name__ == "__main__":
    extract_papers(file_path_authors="people.json")
