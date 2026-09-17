import csv
from urllib.parse import urlparse
from url_scoring import *


def url_parse(x):
    return urlparse(x).netloc


def is_url_in_list(input_url: str, url_list: set):  # DONE: complete this function
    if url_parse(input_url) in url_list:
        return True
    return False


def get_url_blocklist(url_blocklist_path: str = None):
    if not url_blocklist_path:
        url_blocklist_path = "/app/script/urlBlockList/url_blocklist_refinedweb_manual_inspection.csv"
    
    urls_block_list = set()
    
    with open(url_blocklist_path, 'r') as file:
        reader = csv.reader(file)
        for row in reader:
            urls_block_list.add(row[0].strip())
    
    return urls_block_list


def get_url_exclusion(non_web_urls: list = None):
    # Load url domains for non-web data sources
    if not non_web_urls:
        non_web_urls=[
        'https://stackexchange.com/',#stackexchange
        'https://www.ncbi.nlm.nih.gov/pmc/',#pubmed
        # 'https://www.reddit.com/',#OpenWebText2 
        'https://arxiv.org/',#arxiv
        'https://github.com/',#github
        'https://storage.courtlistener.com/',#freelaw
        'https://bulkdata.uspto.gov/',#uspto
        'https://pubmed.ncbi.nlm.nih.gov/',#pubmed
        # 'https://www.gutenberg.org/',#gutenberg
        'https://www.opensubtitles.org/',#opensubtitles
        'https://www.wikipedia.org/',#wikipedia
        'https://irclogs.ubuntu.com/',#ubuntu IRC
        # 'https://www.smashwords.com/books/',#bookscorpus2
        'https://www.statmt.org/', #EuroParl
        'https://news.ycombinator.com/', #hackerNews for comments only
        'https://www.youtube.com/',#youtube subs
        'https://philpapers.org/', #Philpaper
        # 'https://reporter.nih.gov/'#NIH exporter
        ]
    
    urls_exclusion = set()
    
    for url in non_web_urls:
        urls_exclusion.add(url_parse(url))
    
    return urls_exclusion

def get_url_scoring(url_scoring_rules: str = None):
    if not url_scoring_rules:
        url_scoring_rules = "/app/script/urlScoringRules/filtered_scoring_rules.json"

    task = URLScoring()
    params = URLScoringInputParams()
    params.init_params_from_path(url_scoring_rules)
    task.init(params)
    return task


def url_scoring(url, URLS_SCORING_TASK):
    score = URLS_SCORING_TASK.process_url(url) # larger score worse quality
    return score


def url_filtering(url, statistics, threshold, URLS_BLOCK_LIST, URL_EXCLUSION, URLS_SCORING_TASK):
    # 0.2.1 Check if the url is in the url blocklist
    if is_url_in_list(url, URLS_BLOCK_LIST):
        statistics.doc_removed_by_url_blocklist += 1
        return True, None  #, "0.2.1_RefinedWeb_url_blocklist"
    # 0.2.2 Check if the url is in the exclusion list
    if is_url_in_list(url, URL_EXCLUSION):
        statistics.doc_removed_by_url_exclusion += 1
        return True, None  #, "0.2.2_RefinedWeb_url_exclusion"
 
    # # 0.2.3 Perform url scoring
    url_score = url_scoring(url, URLS_SCORING_TASK)
    # if url_score >= threshold.url_score:  # TODO: finalize the function and decide the threshold
    #     statistics.doc_removed_by_url_scoring += 1
    #     return True, None

    return False, url_score  #, None