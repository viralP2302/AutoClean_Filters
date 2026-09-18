from collections import Counter
import logging
from typing import Counter as CounterType
from typing import List, Tuple
from utils import count_sentences
from symbols import *
import numpy as np

symbol_pattern = re.compile("|".join(re.escape(symbol) for symbol in SYMBOLS))
stop_words_pattern = re.compile("|".join(re.escape(symbol) for symbol in STOP_WORDS))

def get_attributes(attrs, text):
    character_count = len(text)
    if character_count == 0:
        return attrs

    try:
        words = text.split()
        word_count = len(words)
        character_count = sum(len(word) for word in words)

        # words = word_tokenize(text)
        # word_count = len([w for w in words if w not in string.punctuation])
        # character_count = sum(len(w) for w in words if w not in string.punctuation)

        
        # 2.3 Statistics-based Heuristics
        attrs.word_count = word_count  # TODO: should we use nltk.tokenize.word_tokenize
        attrs.mean_word_length = character_count / word_count
        # attrs.num_of_sentences = len(SENT_PATTERN.findall(text))
        attrs.num_of_sentences = count_sentences(text)
        # attrs.symbol_to_word_ratio = sum(1 for word in words if any(s in word for s in SYMBOLS)) / word_count
        attrs.symbol_to_word_ratio = sum(1 for word in words if symbol_pattern.search(word)) / word_count
        

        # attrs.fraction_of_words_with_alpha_character = (
        #     sum(1 for word in words if any(c.isalpha() for c in word)) / word_count
        # )
        attrs.fraction_of_words_with_alpha_character = (sum(
            int(ALPH_REGEX.search(word) is not None)
            for word in words
        )) / word_count
        # attrs.num_of_stop_words = sum(1 for word in words if word in STOP_WORDS)
        attrs.num_of_stop_words = sum(1 for word in words if stop_words_pattern.search(word)) 

        # # 2.1 Repetition-based Attributes
        # all_counts = all_ngram_counts(words)

        # count_most_common_ngrams = {2, 3, 4}
        # for n, ngram_counts in all_counts:
        #     if not ngram_counts:
        #         continue
        #     if n in count_most_common_ngrams:
        #         most_common_ngram, count = ngram_counts.most_common(1)[0]
        #         # if count <= 1:
        #         #     attrs.fraction_of_characters_in_most_common_ngram.append((n, 0.0))
        #         # else:
        #         value = count * sum(len(w) for w in most_common_ngram) / character_count
        #         attrs.fraction_of_characters_in_most_common_ngram.append((n, value))
        #     else:
        #         ng_char_count = sum(count * sum(len(w) for w in ng) for ng, count in ngram_counts.items())
        #         value = (
        #             sum((count) * sum(len(w) for w in ng) for ng, count in ngram_counts.items() if count > 1)
        #             / ng_char_count
        #         )
        #         attrs.fraction_of_characters_in_duplicate_ngrams.append((n, value))

        
        all_counts = all_ngram_counts_new(words)
        count_most_common_ngrams = {2, 3, 4}
        for n, ngram_counts in all_counts:
            if not ngram_counts:
                continue
            if n in count_most_common_ngrams:
                most_common_ngram, count = Counter(ngram_counts).most_common(1)[0]
                # if count <= 1:
                #     attrs.fraction_of_characters_in_most_common_ngram.append((n, 0.0))
                # else:
                value = count * sum(len(w) for w in most_common_ngram) / character_count
                attrs.fraction_of_characters_in_most_common_ngram.append((n, value))
            else:
                score = get_dup_ngram_frac(n, ngram_counts, text)
                attrs.fraction_of_characters_in_duplicate_ngrams.append((n, score))


        lines = text.split("\n")
        # lines = line_exp.split(text)
        # lines = paragraph_exp.split(text)
        line_count = len(lines)
        line_counts = Counter(lines)
        attrs.fraction_of_duplicate_lines = (
            sum((count - 1) for _, count in line_counts.items() if count > 1) / line_count
        )
        attrs.fraction_of_characters_in_duplicate_lines = (
            sum(sum(len(w) for w in line.split()) * (count - 1) for line, count in line_counts.items() if count > 1) / character_count
        )

        # paragraphs = paragraph_exp.split(text)
        paragraphs = text.split("\n\n")
        paragraph_count = len(paragraphs)
        if paragraph_count > 1:  # In most cases, we don't have "\n\n"
            paragraphs_counts = Counter(paragraphs)
            attrs.fraction_of_duplicate_paragraphs = (
                sum((count - 1) for _, count in paragraphs_counts.items() if count > 1) / paragraph_count
            )
            attrs.fraction_of_characters_in_duplicate_paragraphs = (
                sum(sum(len(w) for w in paragraph.split()) * (count - 1) for paragraph, count in paragraphs_counts.items() if count > 1) / character_count
            )


        # dup_lines, dup_char = find_dup(lines)
        # attrs.fraction_of_duplicate_lines = dup_lines/line_count
        # attrs.fraction_of_characters_in_duplicate_lines = dup_char / character_count

        if "{" in text or "}" in text:
            attrs.has_curly_bracket = True
        if "lorem ipsum" in text:
            attrs.has_lorem_ipsum = True

    except Exception as e:
        logging.exception(f"Error processing text {e}: {text[:200]}")

    return attrs

def all_ngram_counts(words) -> List[Tuple[int, CounterType[Tuple[str, ...]]]]:
    return [(n, Counter(list(zip(*[words[i:] for i in range(n)])))) for n in range(2, 11)]


def all_ngram_counts_new(words) -> List[Tuple[int, CounterType[Tuple[str, ...]]]]:
    return [(n, list(zip(*[words[i:] for i in range(n)]))) for n in range(2, 11)]


def get_dup_ngram_frac(n, doc_n_grams, text):
    # fetch the ngrams from the document if they exist, otherwise compute them
    # doc_n_grams = list(zip(*[words[i:] for i in range(n)]))

    duplicated_grams = np.zeros(len(text.split()), dtype=int)

    unique_ngrams = set()

    for i, ngram in enumerate(doc_n_grams):
        if ngram in unique_ngrams:
            duplicated_grams[i: i + n] = 1
        else:
            unique_ngrams.add(ngram)

    word_lengths = np.array(list(map(len, text.split())))
    chars_duped = np.sum(word_lengths * duplicated_grams)
    total_chars = np.sum(word_lengths)

    return float(chars_duped / total_chars)


def line_dedup(tmp_data, attrs, threshold):
    text = tmp_data["text"]
    all_lines = []
    all_lines_set = set()
    # for line in line_exp.split(text): 
    for line in text.split("\n"):
    # for line in paragraph_exp.split(text):
        line_norm = line.strip().lower()
        if not line_norm:
            continue
        if line_norm not in all_lines_set:
            all_lines.append(line)
            all_lines_set.add(line_norm)
        elif len(line.split()) <= threshold.min_dup_text_len:
            all_lines.append(line)
        else:
            attrs.orig_text_has_dup_lines = True
    return all_lines
    