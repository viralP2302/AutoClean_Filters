#!/usr/bin/env python

# Copyright 2023 The MBZUAI Data Pipeline Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import re
import json
from ahocorasick import Automaton


# list of regex based on 3 levels of filtering
# 1) filter the URL if the whole URL fuzzy matches any word in strict_subword list, www.gr.oup-sex.com -> groupsex
# 2) filter the URL if its words exact matches any word in hard_whole_word list, www.groupsex-abc -> groupsex
# 3) filter the URL if its words exact matches any 2 words in soft_word list, www.sex-webcam.com -> sex/webcam
# 4) exclude case ass is part of massachusetts
# type:
# punc_free_match - match URL after punctuation are removed
# whole_word_match - match whole original URL directly 
# sub_word_match - match sub words split by punctuation

def is_key_invalid(key, dict_):
    if not dict_.__contains__(key) or dict_[key] == None:
        return True
    return False

# normalize
def normalize(text):
    return text.lower()

DEFAULT_SCORING_RULES = {
    "strict_subword": {
        "regex_list": [
            "groupsex",
            "xvideos"
        ],
        "type": "punc_free_match", 
        "score": 3.0
    },
    "hard_whole_word": {
        "regex_list": [
            "porn"
        ],
        "type": "whole_word_match",
        "score": 3.0
    },
    "soft_word": {
        "regex_list": [
            "bad",
            "ass",
            "dick"
        ],
        "type": "sub_word_match",
        "score": 2.0
    }
}

DEFAULT_SCORING_THRESHOLD = 3.0

class URLSCORING_METHOD:
    DEFAULT = "Default"


class URLScoringInputParams():
    def __init__(self):
        self.__task_type = "URL_SCORING"
        self.__avail_params = {
            'scoring_rules': DEFAULT_SCORING_RULES,
            'threshold': DEFAULT_SCORING_THRESHOLD,
            'method': URLSCORING_METHOD.DEFAULT
        }

    def init_params_from_path(self, params_path):
         with open(params_path) as f:
            param_list = json.load(f)
            self.init_params(param_list)


    def init_params(self, param_list):
            if not self.format_check(param_list):
                raise AssertionError("input params is not expected")
            
            self.__avail_params = param_list

    def format_check(self, param_list):
        if is_key_invalid("scoring_rules", param_list):
            raise AssertionError("no scoring_rules is available")
            return False

        if is_key_invalid("threshold", param_list):
            raise AssertionError("no threshold is available")
            return False
                   
        threshold = param_list["threshold"]
        scoring_rules = param_list["scoring_rules"]
        if not isinstance(scoring_rules, dict):
            return False
    
        for key in scoring_rules.keys():
            if scoring_rules[key]['score'] == None:
                return False
            if scoring_rules[key]['regex_list'] == None:
                return False
            for pattern in scoring_rules[key]['regex_list']:
                if not isinstance(pattern, str):
                    return False  

        return True
    
    def get_scoring_rules(self):
        return self.__avail_params["scoring_rules"]
    
    def get_threshold(self):
        return self.__avail_params["threshold"]
    
    def get_method(self):
        return self.__avail_params["method"]


class URLScoring():

    def init(self, params_in:URLScoringInputParams):
        """init the task with parameters and method used"""
        self.__params = params_in
        self.__method = params_in.get_method()
        self.__automaton_strict_sub_word = Automaton()
        self.__automaton_hard_whole_word = Automaton()
        self.__automaton_sub_word_match  = Automaton()

        if self.__method == URLSCORING_METHOD.DEFAULT:
            # build ahocorasick list
            scoring_rules = self.__params.get_scoring_rules()
            for key in scoring_rules.keys():
                rule_type = scoring_rules[key]["type"]
                regex_list = scoring_rules[key]["regex_list"]
                if rule_type == "sub_word_match":
                    for pattern in regex_list:             
                        self.__automaton_sub_word_match.add_word(pattern, pattern)
                elif rule_type == "whole_word_match":
                    for pattern in regex_list:   
                        self.__automaton_hard_whole_word.add_word(pattern, pattern)
                elif rule_type == "punc_free_match":
                    for pattern in regex_list:   
                        self.__automaton_strict_sub_word.add_word(pattern, pattern)

            self.__automaton_strict_sub_word.make_automaton() 
            self.__automaton_hard_whole_word.make_automaton() 
            self.__automaton_sub_word_match.make_automaton() 


    def process(self, input = None, output = None):
        """
        filter the URL list with score based on keywords.

        Args:
        input: A input params collection consists of following parameters
            1) URL list: list - a URL list to run scoring

        Returns:
        output: A output params collection consists of following parameters
            1) URL list: list - a URL list with output data inserted

        Raises:
        AssertionError: If no available URL list or threshold is found.
        """

        if input == None:
            raise AssertionError("input is invalid")
        
        if isinstance(input, str): # read data from path if it's a path
            task_data = self.read_data(input)
        elif isinstance(input, list):
            task_data = input         

            # filter with rules defined in scoring list
            for index, data in enumerate(task_data):
                self.insert_result(task_data[index]["meta"], ['score'], [self.process_record(data)])

        return task_data


    def process_record(self, record):
        """process one data record"""

        url = record["meta"]["url"]
        return self.process_url(url)
    
    
    def process_url(self, url):

        url = normalize(url)

        scoring_rules = self.__params.get_scoring_rules()
        threshold = self.__params.get_threshold()

        score = 0.0
        words = self.get_words(url)        # get all words with punctuation as separator
        word_punc_free = self.remove_punc(url) # remove punctuation
        for key in scoring_rules.keys():
            rule_type = scoring_rules[key]["type"]
            regex_list = scoring_rules[key]["regex_list"]
            sub_score = scoring_rules[key]["score"]
            if rule_type == "sub_word_match":          
                # perform sub word matching, if any sub-word matches to keyword of scoring list then add score
                matched_words_set = set()  # maintain a set that records keywords get matched, no duplicate keywords in the set
                for word in words:
                    # avoid the case that ass is sub word of massachusetts with compatibility check, maybe we have better method
                    for content in self.__automaton_sub_word_match.iter(word):
                        if content[1] not in matched_words_set:
                        # only penalize once for each soft keyword
                            # matched_words_set.add(content[1])
                            if self.match_compat(content[1], word) >= 0.8:
                                score += sub_score
                                matched_words_set.add(content[1])
                                if score >= threshold:
                                    return score
            elif rule_type == "whole_word_match":
                for content in self.__automaton_hard_whole_word.iter(url):
                # perform whole word matching, if url has any segment matches keyword then add score
                    if len(content[1]) < 4 and content[1]  not in words:  # update: if keyword is less than 4 char, conduct exact matching
                        continue
                    score += sub_score
                    if score >= threshold:
                        return score
            elif rule_type == "punc_free_match":
                for content in self.__automaton_strict_sub_word.iter(word_punc_free):   
                # perform whole word matching after removing punc for fuzzy match
                    score += sub_score
                    if score >= threshold:
                        return score

            if score >= threshold:
                break
 
        return score
    
    def insert_result(self, record, meta_keys:list, meta_values:list):
        """insert the result of processing into one record"""
        for idx in range(len(meta_keys)):
            record[meta_keys[idx]] =meta_values[idx]
  

    # calculate compatibility between pattern and word
    def match_compat(self, pattern, word):
        # Construct the soft word list only containing words’ basic form, (e.g. “face”, no “faces). 
        # because for soft word matching, we’re looking for two different soft words that together can provide sufficient support to filter a URL
        # but problem still exists when pattern="ass", orginal function's result: mass(score=1.0)
        if len(pattern) < 4:  # update: if keyword is less than 4 char, conduct exact matching
            if pattern == word:
                return 1.0
            else:
                return 0.0

        matched = re.search(pattern, word)
        if matched != None:
            compat = float(matched.end() - matched.start())/float(len(word))  # removed "+1" because matched word's index is [start:end)
            if matched.start() == 0 and compat > 0.5:
                # if matched pattern is the start of a word
                return 1.0
            elif (matched.end() == len(word)) and compat > 0.7:  # removed "-1"
                # if mached pattern is the end of a word
                return 1.0

            return compat
        else:
            return 0.0

    def read_data(self, data_path):
        with open(data_path) as f:
            url_list = json.load(f)

    def remove_punc(self, url):
        pattern = r"[^\w]|(?<=\d)\,(?=\d)" # pattern to remove punctuation from URL
        return re.sub(pattern, "", url)


    def get_words(self, url):
        pattern = r'[\W_]+' # splits the URL into words based on non-alphanumeric characters and underscore
        sub_words = re.compile(pattern, re.UNICODE).split(url)
        sub_words = [w for w in sub_words if len(w) > 2]
        return sub_words


    def is_matched(self, pattern, word):
        # if re.search(pattern, word):
        if pattern in word:
            return True
