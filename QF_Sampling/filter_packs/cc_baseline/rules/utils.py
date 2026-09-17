import os
import re
import csv
import gzip
import json
from dataclasses import asdict

from nltk.tokenize import sent_tokenize
from ahocorasick import Automaton


def make_dir(file_name):
    file_path = os.path.dirname(file_name)
    if not os.path.exists(file_path):
        os.makedirs(file_path, exist_ok=True)


def write_stat(stat_file, statistics, input_file, FIELD_NAMES):
    make_dir(stat_file)
    print(f"Writing {str(input_file)} into {stat_file}")
    if not os.path.exists(stat_file):
        with open(stat_file, mode="a", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=FIELD_NAMES)

            # Write the headers
            writer.writeheader()

            # Write the data as a dictionary
            writer.writerow(asdict(statistics))
    else:
        with open(stat_file, mode="a", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=FIELD_NAMES)

            # Write the data as a dictionary
            writer.writerow(asdict(statistics))


def is_counter(input_text):
    pattern = r"^\d+\s+likes$"
    return bool(re.match(pattern, input_text))


def count_sentences(text):
    sentences = sent_tokenize(text)
    return len(sentences)


def get_bad_words_list(bad_words_path=None):
    """Get the bad word list"""
    if not bad_words_path:
        bad_words_path = "/app/script/LDNOOBW"
    bad_words_list = []
    bad_words_to_skip = (
        " am ",
        " fan ",
        " pot ",
        " del ",
        " 13. ",
        " lund ",
        " franc ",
        " mona ",
        " mof ",
    )
    # change "escort" in en to "escort service"

    alpha_pattern = r"[a-zA-Z0-9]"
    for lang in os.listdir(bad_words_path):
        bad_words_file = os.path.join(bad_words_path, lang)
        with open(bad_words_file, "r") as f:
            for line in f:
                if lang not in ("zh", "ja", "th") or re.findall(
                    alpha_pattern, line.strip()
                ):
                    line_to_add = " " + line.strip().lower() + " "
                else:
                    line_to_add = line.strip().lower()
                if line_to_add in bad_words_to_skip:
                    continue
                if line_to_add == " mona " or line_to_add == " franc ":
                    print(lang)
                    print(line_to_add)
                bad_words_list.append(line_to_add)
    return bad_words_list


def build_automaton(words):
    A = Automaton()
    for word in words:
        A.add_word(word, word)
    A.make_automaton()
    return A


def contains_bad_word(automaton, text):
    for _ in automaton.iter(text):
        return True  # Return True as soon as the first bad word is found
    return False


def get_bad_word_num(automaton, text):
    match_num = 0
    for _ in automaton.iter(text):
        match_num += 1
    return match_num


def remove_file(file_name):
    if os.path.isfile(file_name):
        os.remove(file_name)
        print(f"Remove halfly-processed file: {file_name}")


def write_to_jsonlgz(data, output_file):
    with gzip.open(output_file, "at", encoding="utf-8") as gz_file:
        for item in data:  # one line per item to avoid memory peaks
            gz_file.write(json.dumps(item) + "\n")
