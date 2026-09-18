from dataclasses import dataclass, field
from typing import List, Tuple

@dataclass
class DataAttributes:
    # 0.2.3 URL scores
    url_score : float = 0.0

    # 2.1 Repetition-based Attributes
    fraction_of_duplicate_lines: float = 0.0
    fraction_of_characters_in_duplicate_lines: float = 0.0
    fraction_of_duplicate_paragraphs: float = 0.0
    fraction_of_characters_in_duplicate_paragraphs: float = 0.0
    fraction_of_characters_in_most_common_ngram: List[Tuple[int, float]] = field(
        default_factory=list
    )
    fraction_of_characters_in_duplicate_ngrams: List[Tuple[int, float]] = field(
        default_factory=list
    )
    
    # 2.2 Line-wise Heuristics
    fraction_of_words_corrected_in_lines: float = 0.0
    fraction_of_lines_ending_with_ellipsis: float = 0.0
    fraction_of_lines_starting_with_bullet_point: float = 0.0
    fraction_of_lines_with_toxic_words: float = 0.0
    num_of_lines_with_toxic_words: int = 0
    num_of_toxic_words: int = 0

    # 2.3 Statistics-based Heuristics
    word_count: int = 0
    mean_word_length: float = 0.0
    num_of_sentences: int = 0
    symbol_to_word_ratio: float = 0.0
    fraction_of_words_with_alpha_character: float = 0.0
    num_of_stop_words: int = 0
    num_of_paragraphs: int = 0  # TODO: may not use this attribute

    # 2.4 Others
    has_curly_bracket: bool = False
    has_lorem_ipsum: bool = False

    # 3.1
    orig_text_has_dup_lines: bool = False



@dataclass
class DataStatistics:
    file_path: str = None
    doc_all: int = 0
    doc_en: int = 0
    doc_removed_by_url_blocklist: int = 0
    doc_removed_by_url_exclusion: int = 0
    doc_removed_by_url_scoring: int = 0
    doc_empty_by_line_correction: int = 0
    doc_removed_by_line_dup_frac: int = 0
    doc_removed_by_line_dup_char_frac: int = 0
    doc_removed_by_para_dup_frac: int = 0
    doc_removed_by_para_dup_char_frac: int = 0
    doc_removed_by_common_ngram: int = 0
    doc_removed_by_dup_ngram: int = 0
    doc_removed_by_repetition: int = 0
    doc_removed_by_ending_ellipsis: int = 0
    doc_removed_by_starting_bullet: int = 0
    doc_removed_by_word_count: int = 0
    doc_removed_by_mean_word_length: int = 0
    doc_removed_by_num_of_sentences: int = 0
    doc_removed_by_symbol_to_word_ratio: int = 0
    doc_removed_by_alpha_charcter: int = 0
    doc_removed_by_num_of_stop_words: int = 0
    doc_removed_by_curly_bracket: int = 0
    doc_removed_by_lorem_ipsum: int = 0
    doc_removed_by_doc_wise_filtering: int = 0
    doc_removed_by_line_correction: int = 0
    doc_removed_by_toxic_content: int = 0
    doc_has_duplicated_lines: int = 0
    doc_remaining: int = 0