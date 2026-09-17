from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class DataThreshold:
    # 0.1 Language score
    lang_score: int = 0.65
    
    # 0.2.3 URL score
    url_score : float = 3.0
    
    # 1.3.4 Line-Level Threshold
    min_word_count_per_line: int = 1

    # 2.1 Repetition-based Attributes
    fraction_of_duplicate_lines: float = 0.3
    fraction_of_characters_in_duplicate_lines: float = 0.2
    fraction_of_duplicate_paragraphs: float = 0.3
    fraction_of_characters_in_duplicate_paragraphs: float = 0.2
    fraction_of_characters_in_most_common_ngram: List[Tuple[int, float]] = field(
        default_factory=lambda: [
            # (2, 0.25),
            # (3, 0.23),
            # (4, 0.21),
            (2, 0.20),
            (3, 0.18),
            (4, 0.16),
            # (5, 0.15),
            # (6, 0.14),
        ]
    )
    fraction_of_characters_in_duplicate_ngrams: List[Tuple[int, float]] = field(
        default_factory=lambda: [
            # (5, 0.20),
            # (6, 0.19),
            # (7, 0.18),
            # (8, 0.17),
            # (9, 0.16),
            # (10, 0.15)
            (5, 0.15),
            (6, 0.14),
            (7, 0.13),
            (8, 0.12),
            (9, 0.11),
            (10, 0.10)
        ]
    )

    # 2.2 Line-wise Heuristics
    fraction_of_words_corrected_in_lines: float = 0.05
    fraction_of_lines_ending_with_ellipsis: float = 0.30
    fraction_of_lines_starting_with_bullet_point: float = 0.90
    fraction_of_lines_with_toxic_words: float = 0.10
    num_of_lines_with_toxic_words: int = 8
    num_of_toxic_words: int = 10

    # 2.3 Statistics-based Heuristics
    word_count: Tuple = (50, 100000)  # Lowerbound and Upperbound
    mean_word_length: Tuple = (3.0, 10.0)  # Lowerbound and Upperbound
    num_of_sentences: int = 3
    symbol_to_word_ratio: float = 0.1
    fraction_of_words_with_alpha_character: float = 0.8
    num_of_stop_words: int = 2
    num_of_paragraphs: int = 0  # TODO: may not use this attribute

    # 2.4 Others
    has_curly_bracket: bool = False
    has_lorem_ipsum: bool = True

    # 3.1 Line-Level refinement
    min_dup_text_len: int = 20