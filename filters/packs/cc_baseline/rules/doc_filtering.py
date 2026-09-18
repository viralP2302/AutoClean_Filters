
def doc_filtering_repetition(attrs, threshold, statistics):
    statistics.doc_removed_by_repetition += 1
    # 2.1.1 Remove any document if the fraction of duplicate lines exceeds 30%
    if attrs.fraction_of_duplicate_lines > threshold.fraction_of_duplicate_lines:
        statistics.doc_removed_by_line_dup_frac += 1
        return True  #, "2.1.1_Gopher_frac_duplicate_lines"
    # 2.1.2 Remove any document if the fraction of characters in duplicated lines exceeds 30%
    if attrs.fraction_of_characters_in_duplicate_lines > threshold.fraction_of_characters_in_duplicate_lines:
        statistics.doc_removed_by_line_dup_char_frac += 1
        return True  #, "2.1.2_Gopher_frac_char_duplicate_lines"
    # 2.1.1 Remove any document if the fraction of duplicate paragraphs exceeds 30%
    if attrs.fraction_of_duplicate_paragraphs > threshold.fraction_of_duplicate_paragraphs:
        statistics.doc_removed_by_para_dup_frac += 1
        return True  #, "2.1.1_Gopher_frac_duplicate_paragraphs"
    # 2.1.2 Remove any document if the fraction of characters in duplicated paragraphs exceeds 30%
    if attrs.fraction_of_characters_in_duplicate_paragraphs > threshold.fraction_of_characters_in_duplicate_paragraphs:
        statistics.doc_removed_by_para_dup_char_frac += 1
        return True  #, "2.1.2_Gopher_frac_char_duplicate_paragraphs"

    # 2.1.3 Remove any document if the fraction of characters in the most common n-gram exceeds the given threshold
    common_ngram_tag = False
    for (_, frac), (_, frac_threshold) in zip(attrs.fraction_of_characters_in_most_common_ngram, threshold.fraction_of_characters_in_most_common_ngram):
        if frac > frac_threshold:
            statistics.doc_removed_by_common_ngram += 1
            common_ngram_tag = True
            break
    if common_ngram_tag:
        return True  #, "2.1.3_Gopher_frac_char_common_ngram"
    dup_ngram_tag = False
    # 2.1.3 Remove any document if the fraction of characters in the most common n-gram exceeds the given threshold
    for (_, frac), (_, frac_threshold) in zip(attrs.fraction_of_characters_in_duplicate_ngrams, threshold.fraction_of_characters_in_duplicate_ngrams):
        if frac > frac_threshold:
            statistics.doc_removed_by_dup_ngram += 1
            dup_ngram_tag = True
            break
    if dup_ngram_tag:
        return True  #, "2.1.3_Gopher_frac_char_dup_ngram"

    statistics.doc_removed_by_repetition -= 1
    return False  #, None


def doc_filtering_docwise(attrs, threshold, statistics):
    statistics.doc_removed_by_doc_wise_filtering += 1
   
    # 2.2 Line-wise Heuristics Filtering
    # # 2.2.1 Remove the documents in corrected lines represent more than 5% words
    # if attrs.fraction_of_words_corrected_in_lines > threshold.fraction_of_words_corrected_in_lines:
    #     continue
    # # --> Leave 2.2.1 later to align with RefinedWeb
    
    # 2.2.2 Remove any document with more than 30% of the lines ending with an ellipsis
    if attrs.fraction_of_lines_ending_with_ellipsis > threshold.fraction_of_lines_ending_with_ellipsis:
        statistics.doc_removed_by_ending_ellipsis += 1
        return True
    # 2.2.3 Remove any document with more than 90% of lines starting with a bullet point
    if attrs.fraction_of_lines_starting_with_bullet_point > threshold.fraction_of_lines_starting_with_bullet_point:
        statistics.doc_removed_by_starting_bullet += 1
        return True


    # 2.3 Statistics-based Heuristics Filtering
    # 2.3.1 Remove any document whose word count is not in a target range
    if attrs.word_count < threshold.word_count[0] or attrs.word_count > threshold.word_count[1]:
        statistics.doc_removed_by_word_count += 1
        return True
    # 2.3.2 Remove any document whose mean word length is outside the range of 3 to 10 characters
    if attrs.mean_word_length < threshold.mean_word_length[0] or attrs.mean_word_length > threshold.mean_word_length[1]:
        statistics.doc_removed_by_mean_word_length += 1
        return True
    # 2.3.3 Remove any document with fewer than 3 sentences
    if attrs.num_of_sentences < threshold.num_of_sentences:
        statistics.doc_removed_by_num_of_sentences += 1
        return True
    # 2.3.4 Remove any document with a symbol-to-word ratio greater than 0.1 for either the hash symbol or the ellipsis
    if attrs.symbol_to_word_ratio > threshold.symbol_to_word_ratio:
        statistics.doc_removed_by_symbol_to_word_ratio += 1
        return True
    # 2.3.5 Require that 80% of words in a document contain at least one alphabetic character
    if attrs.fraction_of_words_with_alpha_character < threshold.fraction_of_words_with_alpha_character:
        statistics.doc_removed_by_alpha_charcter += 1
        return True
    # 2.3.6 Remove documents that do not contain at least two of the given stop words
    if attrs.num_of_stop_words < threshold.num_of_stop_words:
        statistics.doc_removed_by_num_of_stop_words += 1
        return True

    # 2.4 Others
    # 2.4.1 Remove any document if it contains a curly bracket
    if threshold.has_curly_bracket and attrs.has_curly_bracket:
        statistics.doc_removed_by_curly_bracket += 1
        return True
    # 2.4.2 Remove any document where the phrase “lorem ipsum” appeared
    if threshold.has_lorem_ipsum and attrs.has_lorem_ipsum:
        statistics.doc_removed_by_lorem_ipsum += 1
        return True

    statistics.doc_removed_by_doc_wise_filtering -= 1
    return False

def doc_filtering_line_correction(attrs, threshold, statistics):
    if attrs.fraction_of_words_corrected_in_lines > threshold.fraction_of_words_corrected_in_lines:
        statistics.doc_removed_by_line_correction += 1
        return True
    return False

def doc_filtering_toxicity(attrs, threshold, statistics):
    # TODO: refine this function
    if attrs.num_of_lines_with_toxic_words > threshold.num_of_lines_with_toxic_words:
        statistics.doc_removed_by_toxic_content += 1
        return True
    if attrs.num_of_toxic_words > threshold.num_of_toxic_words:
        statistics.doc_removed_by_toxic_content += 1
        return True
    return False